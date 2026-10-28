"""Async MAGPIE RPC responder over ZMTP ROUTER connections."""

import asyncio
import time

from ..rpc_responder import RpcResponder
from .zmq_common import Mailbox, parse_endpoint
from .zmtp import ZmtpPeer


class ZmqRpcResponder(RpcResponder):
    """Serve desktop MAGPIE DEALER callers, one handler call at a time."""

    def __init__(self, endpoint, serializer=None, schema=None, bind=True,
                 queue_size=4, max_peers=4, max_message_size=8192):
        if queue_size < 1 or max_peers < 1:
            raise ValueError("queue_size and max_peers must be positive")
        super().__init__(schema=schema)
        if serializer is None:
            from ...serializer.msgpack_serializer import MsgpackSerializer
            serializer = MsgpackSerializer()
        self._serializer = serializer
        self._host, self._port = parse_endpoint(endpoint, bind)
        self._bind = bind
        self._max_peers = max_peers
        self._max_message_size = max_message_size
        self._mailbox = Mailbox(queue_size)
        self._server = None
        self._client_task = None
        self._peers = set()
        self._opening = 0
        self._busy = False
        self.malformed = 0

    @property
    def dropped(self):
        return self._mailbox.dropped

    async def start(self):
        if self._closed:
            raise RuntimeError("responder is closed")
        if self._bind:
            if self._server is None:
                self._server = await asyncio.start_server(
                    self._accept, self._host, self._port)
        elif self._client_task is None:
            self._client_task = asyncio.create_task(self._connect_loop())
        return self

    async def _accept(self, reader, writer):
        if self._closed or len(self._peers) + self._opening >= self._max_peers:
            writer.close()
            await writer.wait_closed()
            return
        self._opening += 1
        try:
            await self._serve_peer(reader, writer)
        finally:
            self._opening -= 1

    async def _connect_loop(self):
        while not self._closed:
            try:
                reader, writer = await asyncio.open_connection(self._host, self._port)
                await self._serve_peer(reader, writer)
            except asyncio.CancelledError:
                break
            except Exception:
                pass
            if not self._closed:
                await asyncio.sleep(1)

    async def _serve_peer(self, reader, writer):
        peer = ZmtpPeer(reader, writer, "ROUTER",
                        max_frame_size=self._max_message_size,
                        max_message_size=self._max_message_size)
        try:
            await asyncio.wait_for(peer.handshake(), 10)
            if self._closed or len(self._peers) >= self._max_peers:
                return
            self._peers.add(peer)
            while not self._closed:
                kind, parts = await peer.recv_event()
                if kind == "message" and len(parts) == 1:
                    # A full queue omits ACK. The caller then sees ACK timeout.
                    self._mailbox.put((peer, parts[0]))
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            self._peers.discard(peer)
            await peer.close()

    async def respond(self, handler=None, timeout=None):
        if self._busy:
            raise RuntimeError("respond() is already active")
        self._busy = True
        try:
            await self.start()
            return await super().respond(handler=handler, timeout=timeout)
        finally:
            self._busy = False

    async def _transport_recv(self, timeout):
        started = time.ticks_ms() if hasattr(time, "ticks_ms") else time.monotonic()
        while True:
            if timeout is None:
                remaining = None
            elif hasattr(time, "ticks_ms"):
                remaining = timeout - time.ticks_diff(time.ticks_ms(), started) / 1000
            else:
                remaining = timeout - (time.monotonic() - started)
            if remaining is not None and remaining <= 0:
                raise asyncio.TimeoutError("no valid ZMQ RPC request")
            peer, payload = await self._mailbox.get(remaining)
            if peer not in self._peers:
                continue
            try:
                message = self._serializer.deserialize(payload)
            except Exception:
                self.malformed += 1
                continue
            if (not isinstance(message, dict) or
                    not isinstance(message.get("rid"), str) or
                    not message["rid"] or "payload" not in message):
                self.malformed += 1
                continue
            rid = message["rid"]
            try:
                await peer.send_multipart((self._serializer.serialize(
                    {"rid": rid, "ack": True}),))
            except OSError:
                self._peers.discard(peer)
                await peer.close()
                continue
            return message["payload"], (peer, rid)

    async def _transport_send(self, response_obj, context):
        peer, rid = context
        if peer not in self._peers:
            raise RuntimeError("ZMQ RPC caller disconnected")
        payload = self._serializer.serialize({"rid": rid, "payload": response_obj})
        await peer.send_multipart((payload,))

    async def _transport_close(self):
        self._mailbox.close()
        if self._server is not None:
            self._server.close()
        for peer in tuple(self._peers):
            await peer.close()
        self._peers.clear()
        if self._server is not None:
            await self._server.wait_closed()
            self._server = None
        if self._client_task is not None:
            self._client_task.cancel()
            try:
                await self._client_task
            except asyncio.CancelledError:
                pass
            self._client_task = None

