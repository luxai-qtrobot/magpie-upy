"""Asynchronous ZMTP SUB stream reader for MicroPython."""

import asyncio

from ..stream_reader import StreamReader
from .zmq_common import Mailbox, parse_endpoint
from .zmtp import ZmtpPeer


class ZmqStreamReader(StreamReader):
    """Receive MAGPIE's [topic, payload] PUB/SUB messages.

    Topic subscriptions are byte prefixes, as in desktop ZeroMQ. A zero
    queue_size avoids an additional application buffer but still needs one
    ingress slot for asynchronous TCP reads and multiple publishers. In
    latest mode, read() discards older buffered messages and returns the
    newest one; this is a small-device approximation of desktop RCVHWM=1.
    """

    def __init__(self, endpoint, topic="", serializer=None, queue_size=4,
                 bind=False, delivery="reliable", max_message_size=8192,
                 max_peers=4):
        if delivery not in ("reliable", "latest"):
            raise ValueError("delivery must be 'reliable' or 'latest'")
        if queue_size < 0 or max_message_size < 1 or max_peers < 1:
            raise ValueError("queue_size, max_message_size or max_peers is invalid")
        if isinstance(topic, str):
            topics = (topic,)
        elif isinstance(topic, (tuple, list)) and topic:
            topics = tuple(topic)
        else:
            raise ValueError("topic must be a string or a nonempty list")
        if not all(isinstance(item, str) for item in topics):
            raise ValueError("topics must be strings")
        super().__init__(serializer=serializer)
        self._host, self._port = parse_endpoint(endpoint, bind)
        self._bind = bind
        self._topics = tuple(item.encode() for item in topics)
        self._delivery = delivery
        self._max_message_size = max_message_size
        self._max_peers = max_peers
        self._mailbox = Mailbox(max(1, queue_size))
        self._peers = []
        self._pending = []
        self._server = None
        self._accept_tasks = []
        self._client_task = None
        self._connected = asyncio.Event()
        self._started = False

    @property
    def dropped(self):
        return self._mailbox.dropped

    async def start(self):
        if self._closed:
            raise RuntimeError("reader is closed")
        if self._started:
            return self
        self._started = True
        try:
            if self._bind:
                self._server = await asyncio.start_server(
                    self._serve_accepted, self._host, self._port)
            else:
                self._client_task = asyncio.create_task(self._connect_loop())
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
                pass
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
        peer = ZmtpPeer(reader, writer, "SUB",
                        max_frame_size=self._max_message_size,
                        max_message_size=self._max_message_size, max_parts=2)
        registered = False
        if self._closed or len(self._peers) + len(self._pending) >= self._max_peers:
            await peer.close()
            return
        self._pending.append(peer)
        try:
            await asyncio.wait_for(peer.handshake(), 10)
            if peer.remote_type != "PUB":
                return
            self._peers.append(peer)
            registered = True
            for topic in self._topics:
                await peer.subscribe(topic)
            self._connected.set()
            while not self._closed:
                kind, parts = await peer.recv_event()
                if kind != "message" or len(parts) != 2:
                    continue
                topic_bytes, payload = parts
                if not any(topic_bytes.startswith(prefix) for prefix in self._topics):
                    continue
                try:
                    topic = topic_bytes.decode()
                except UnicodeError:
                    continue
                self._mailbox.put((payload, topic), drop_oldest=True)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        finally:
            if peer in self._pending:
                self._pending.remove(peer)
            if registered:
                if peer in self._peers:
                    self._peers.remove(peer)
                if not self._peers:
                    self._connected.clear()
            await peer.close()

    async def _transport_read(self, timeout):
        await self.start()
        return await self._mailbox.get(timeout, latest=self._delivery == "latest")

    async def _transport_close(self):
        self._mailbox.close()
        if self._client_task is not None:
            self._client_task.cancel()
        if self._server is not None:
            self._server.close()
        for peer in tuple(self._peers):
            await peer.close()
        for peer in tuple(self._pending):
            await peer.close()
        self._peers.clear()
        self._connected.clear()
        if self._server is not None and hasattr(self._server, "wait_closed"):
            await self._server.wait_closed()
        if self._client_task is not None:
            try:
                await self._client_task
            except asyncio.CancelledError:
                pass
        for task in tuple(self._accept_tasks):
            try:
                await task
            except asyncio.CancelledError:
                pass
