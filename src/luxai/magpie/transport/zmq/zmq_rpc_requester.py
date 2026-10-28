"""Async MAGPIE RPC requester over a ZMTP DEALER connection."""

import asyncio
import binascii
import os

from ..rpc_requester import RpcRequester, AckTimeoutError, ReplyTimeoutError
from .zmq_common import parse_endpoint
from .zmtp import ZmtpPeer


class _Pending:
    def __init__(self):
        self.ack = asyncio.Event()
        self.done = asyncio.Event()
        self.payload = None
        self.error = None


class ZmqRpcRequester(RpcRequester):
    """Call a desktop MAGPIE ROUTER; failed calls are never replayed."""

    def __init__(self, endpoint, serializer=None, schema=None, identity=None,
                 ack_timeout=2, reply_timeout=10, max_pending=4,
                 max_message_size=8192):
        if max_pending < 1 or ack_timeout <= 0 or reply_timeout <= 0:
            raise ValueError("max_pending and timeouts must be positive")
        super().__init__(schema=schema)
        if serializer is None:
            from ...serializer.msgpack_serializer import MsgpackSerializer
            serializer = MsgpackSerializer()
        self._serializer = serializer
        self._host, self._port = parse_endpoint(endpoint, False)
        self._identity = identity
        self._ack_timeout = ack_timeout
        self._reply_timeout = reply_timeout
        self._max_pending = max_pending
        self._max_message_size = max_message_size
        self._instance_id = binascii.hexlify(os.urandom(6)).decode()
        self._next_id = 0
        self._pending = {}
        self._connected = asyncio.Event()
        self._peer = None
        self._task = None

    async def start(self):
        if self._closed:
            raise RuntimeError("requester is closed")
        if self._task is None:
            self._task = asyncio.create_task(self._connect_loop())
        return self

    def _fail_pending(self, error):
        for pending in self._pending.values():
            pending.error = error
            pending.ack.set()
            pending.done.set()

    async def _connect_loop(self):
        while not self._closed:
            peer = None
            was_connected = False
            try:
                reader, writer = await asyncio.open_connection(self._host, self._port)
                peer = ZmtpPeer(reader, writer, "DEALER", identity=self._identity,
                                max_frame_size=self._max_message_size,
                                max_message_size=self._max_message_size)
                await asyncio.wait_for(peer.handshake(), 10)
                self._peer = peer
                was_connected = True
                self._connected.set()
                while not self._closed:
                    kind, parts = await peer.recv_event()
                    if kind != "message" or len(parts) != 1:
                        continue
                    try:
                        message = self._serializer.deserialize(parts[0])
                    except Exception:
                        continue
                    if not isinstance(message, dict):
                        continue
                    pending = self._pending.get(message.get("rid"))
                    if pending is None:
                        continue
                    if message.get("ack") is True:
                        pending.ack.set()
                    elif "payload" in message:
                        pending.payload = message["payload"]
                        pending.ack.set()
                        pending.done.set()
            except asyncio.CancelledError:
                break
            except Exception:
                pass
            finally:
                self._connected.clear()
                if self._peer is peer:
                    self._peer = None
                if peer is not None:
                    await peer.close()
                if was_connected:
                    self._fail_pending(RuntimeError("ZMQ RPC connection lost"))
            if not self._closed:
                await asyncio.sleep(1)

    async def _transport_call(self, request_obj, timeout):
        await self.start()
        if len(self._pending) >= self._max_pending:
            raise RuntimeError("too many ZMQ RPC calls in progress")
        if timeout is None:
            timeout = self._reply_timeout
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._next_id += 1
        rid = "%s-%x" % (self._instance_id, self._next_id)
        pending = _Pending()
        self._pending[rid] = pending
        try:
            try:
                await asyncio.wait_for(self._connected.wait(),
                                       min(timeout, self._ack_timeout))
            except asyncio.TimeoutError:
                raise AckTimeoutError("ZMQ RPC peer is unavailable")
            peer = self._peer
            if peer is None:
                raise AckTimeoutError("ZMQ RPC peer disconnected")
            payload = self._serializer.serialize({"rid": rid, "payload": request_obj})
            try:
                await asyncio.wait_for(peer.send_multipart((payload,)),
                                       min(timeout, self._ack_timeout))
            except asyncio.TimeoutError:
                await peer.close()
                raise AckTimeoutError("ZMQ RPC send timed out")
            try:
                await asyncio.wait_for(pending.ack.wait(),
                                       min(timeout, self._ack_timeout))
            except asyncio.TimeoutError:
                raise AckTimeoutError("no ZMQ RPC ACK")
            if pending.error is not None:
                raise pending.error
            try:
                await asyncio.wait_for(pending.done.wait(), timeout)
            except asyncio.TimeoutError:
                raise ReplyTimeoutError("no ZMQ RPC reply")
            if pending.error is not None:
                raise pending.error
            return pending.payload
        finally:
            self._pending.pop(rid, None)

    async def _transport_close(self):
        self._connected.clear()
        self._fail_pending(RuntimeError("ZMQ RPC requester is closed"))
        if self._peer is not None:
            await self._peer.close()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._pending.clear()

