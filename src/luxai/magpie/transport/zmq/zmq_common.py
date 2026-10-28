"""Small TCP endpoint and bounded mailbox helpers for ZMQ transports."""

import asyncio


def parse_endpoint(endpoint, bind=False):
    """Return (host, port) for the supported tcp:// ZMQ endpoints."""
    if not isinstance(endpoint, str) or not endpoint.startswith("tcp://"):
        raise ValueError("ZMQ endpoint must start with tcp://")
    address = endpoint[6:]
    if address.startswith("["):
        end = address.find("]")
        if end < 0 or address[end + 1:end + 2] != ":":
            raise ValueError("invalid ZMQ TCP endpoint")
        host, port_text = address[1:end], address[end + 2:]
    else:
        host, sep, port_text = address.rpartition(":")
        if not sep or ":" in host:
            raise ValueError("invalid ZMQ TCP endpoint")
    if not host or not port_text.isdigit():
        raise ValueError("invalid ZMQ TCP endpoint")
    port = int(port_text)
    if not 0 < port < 65536:
        raise ValueError("ZMQ TCP port must be in 1..65535")
    if host == "*":
        if not bind:
            raise ValueError("tcp://* is only valid when binding")
        host = "0.0.0.0"
    return host, port


class Mailbox:
    """Bounded async mailbox; no worker task or extra queue is created."""

    def __init__(self, limit):
        if limit < 1:
            raise ValueError("mailbox limit must be positive")
        self._limit = limit
        self._items = []
        self._ready = asyncio.Event()
        self._closed = False
        self.dropped = 0

    def put(self, item, drop_oldest=False):
        if self._closed:
            return False
        if len(self._items) >= self._limit:
            self.dropped += 1
            if not drop_oldest:
                return False
            self._items.pop(0)
        self._items.append(item)
        self._ready.set()
        return True

    async def get(self, timeout=None, latest=False):
        while not self._items:
            if self._closed:
                raise RuntimeError("mailbox is closed")
            self._ready.clear()
            if timeout is None:
                await self._ready.wait()
            else:
                await asyncio.wait_for(self._ready.wait(), timeout)
        if latest:
            item = self._items[-1]
            self.dropped += len(self._items) - 1
            self._items.clear()
            return item
        return self._items.pop(0)

    def close(self):
        self._closed = True
        self._items.clear()
        self._ready.set()
