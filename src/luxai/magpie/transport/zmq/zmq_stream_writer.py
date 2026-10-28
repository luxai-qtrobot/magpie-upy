"""Asynchronous ZMTP PUB stream writer for MicroPython."""

import asyncio

from ..stream_writer import StreamWriter
from ...utils import Logger
from .zmq_common import Mailbox, parse_endpoint
from .zmtp import ZmtpPeer


class ZmqStreamWriter(StreamWriter):
    """Publish MAGPIE's two-frame [topic, payload] messages over TCP.

    ``queue_size`` controls an optional application queue. Each connected SUB
    also has a small, bounded send queue so a slow peer cannot hold up others.
    PUB/SUB is best effort in both delivery modes.
    """

    def __init__(self, endpoint, serializer=None, queue_size=0, bind=True,
                 delivery="reliable", max_message_size=8192, max_peers=4,
                 max_subscriptions=16, max_subscription_bytes=512):
        if delivery not in ("reliable", "latest"):
            raise ValueError("delivery must be 'reliable' or 'latest'")
        if (queue_size < 0 or max_message_size < 1 or max_peers < 1 or
                max_subscriptions < 1 or max_subscription_bytes < 1):
            raise ValueError("invalid ZMQ stream limit")
        super().__init__(serializer=serializer)
        self._host, self._port = parse_endpoint(endpoint, bind)
        self._bind = bind
        self._delivery = delivery
        self._max_message_size = max_message_size
        self._max_peers = max_peers
        self._max_subscriptions = max_subscriptions
        self._max_subscription_bytes = max_subscription_bytes
        self._peers = []
        self._pending = []
        self._server = None
        self._accept_tasks = []
        self._client_task = None
        self._app_queue = Mailbox(queue_size) if queue_size else None
        self._app_task = None
        self._connected = asyncio.Event()
        self._started = False
        self.dropped = 0

    async def start(self):
        if self._closed:
            raise RuntimeError("writer is closed")
        if self._started:
            return self
        self._started = True
        try:
            if self._bind:
                self._server = await asyncio.start_server(
                    self._serve_accepted, self._host, self._port)
            else:
                self._client_task = asyncio.create_task(self._connect_loop())
            if self._app_queue is not None:
                self._app_task = asyncio.create_task(self._app_loop())
        except Exception:
            self._started = False
            raise
        return self

    async def wait_connected(self, timeout=None):
        await self.start()
        if timeout is None:
            await self._connected.wait()
        else:
            await asyncio.wait_for(self._connected.wait(), timeout)
        return self

    async def _connect_loop(self):
        delay = 0.25
        while not self._closed:
            try:
                reader, writer = await asyncio.open_connection(self._host, self._port)
                delay = 0.25
                await self._serve_stream(reader, writer)
            except asyncio.CancelledError:
                return
            except Exception:
                pass  # Network loss is retried; Wi-Fi itself belongs to the app.
            if not self._closed:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 5)

    async def _serve_accepted(self, reader, writer):
        task = asyncio.current_task()
        self._accept_tasks.append(task)
        try:
            await self._serve_stream(reader, writer)
        finally:
            if task in self._accept_tasks:
                self._accept_tasks.remove(task)

    async def _serve_stream(self, reader, writer):
        peer = ZmtpPeer(reader, writer, "PUB",
                        max_frame_size=self._max_message_size,
                        max_message_size=self._max_message_size, max_parts=2)
        entry = None
        if self._closed or len(self._peers) + len(self._pending) >= self._max_peers:
            await peer.close()
            return
        self._pending.append(peer)
        try:
            await asyncio.wait_for(peer.handshake(), 10)
            if peer.remote_type != "SUB":
                return
            entry = {"peer": peer, "subs": {}, "sub_count": 0, "sub_bytes": 0,
                     "queue": Mailbox(1 if self._delivery == "latest" else 4)}
            self._peers.append(entry)
            self._connected.set()
            entry["task"] = asyncio.create_task(self._send_loop(entry))
            while not self._closed:
                kind, topic = await peer.recv_event()
                if kind == "subscribe":
                    count = entry["subs"].get(topic, 0)
                    if (entry["sub_count"] >= self._max_subscriptions or
                            (not count and entry["sub_bytes"] + len(topic) >
                             self._max_subscription_bytes)):
                        return
                    entry["subs"][topic] = count + 1
                    entry["sub_count"] += 1
                    if not count:
                        entry["sub_bytes"] += len(topic)
                elif kind == "cancel":
                    count = entry["subs"].get(topic, 0)
                    if count == 1:
                        entry["subs"].pop(topic, None)
                        entry["sub_bytes"] -= len(topic)
                    elif count > 1:
                        entry["subs"][topic] = count - 1
                    if count:
                        entry["sub_count"] -= 1
        except asyncio.CancelledError:
            pass
        except Exception:
            pass  # A peer that disconnects must not interrupt other subscribers.
        finally:
            if peer in self._pending:
                self._pending.remove(peer)
            if entry is not None:
                if entry in self._peers:
                    self._peers.remove(entry)
                entry["queue"].close()
                entry["task"].cancel()
                try:
                    await entry["task"]
                except asyncio.CancelledError:
                    pass
                if not self._peers:
                    self._connected.clear()
            await peer.close()

    async def _send_loop(self, entry):
        try:
            while not self._closed:
                parts = await entry["queue"].get()
                await entry["peer"].send_multipart(parts)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            Logger.warning("ZMQ subscriber send failed: {}".format(exc))
            await entry["peer"].close()

    def _fanout(self, parts):
        topic = parts[0]
        for entry in self._peers:
            if any(topic.startswith(prefix) for prefix in entry["subs"]):
                before = entry["queue"].dropped
                entry["queue"].put(parts,
                                   drop_oldest=self._delivery == "latest")
                self.dropped += entry["queue"].dropped - before

    async def _app_loop(self):
        try:
            while not self._closed:
                self._fanout(await self._app_queue.get())
        except asyncio.CancelledError:
            pass
        except RuntimeError:
            pass

    async def _transport_write(self, payload, topic):
        await self.start()
        topic_bytes = topic.encode()
        if len(topic_bytes) + len(payload) > self._max_message_size:
            raise ValueError("ZMQ message exceeds configured limit")
        parts = (topic_bytes, payload)
        if self._app_queue is None:
            self._fanout(parts)
        else:
            before = self._app_queue.dropped
            self._app_queue.put(parts, drop_oldest=True)
            self.dropped += self._app_queue.dropped - before

    async def _transport_close(self):
        if self._app_queue is not None:
            self._app_queue.close()
        if self._app_task is not None:
            self._app_task.cancel()
        if self._client_task is not None:
            self._client_task.cancel()
        if self._server is not None:
            self._server.close()
        send_tasks = []
        for entry in tuple(self._peers):
            entry["queue"].close()
            entry["task"].cancel()
            send_tasks.append(entry["task"])
            await entry["peer"].close()
        for peer in tuple(self._pending):
            await peer.close()
        self._peers.clear()
        self._connected.clear()
        if self._server is not None and hasattr(self._server, "wait_closed"):
            await self._server.wait_closed()
        for task in (self._client_task, self._app_task):
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        for task in send_tasks + list(self._accept_tasks):
            try:
                await task
            except asyncio.CancelledError:
                pass
