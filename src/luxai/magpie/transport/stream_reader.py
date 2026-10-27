"""Transport-independent asynchronous stream reader."""

class StreamReader:
    """Read values and topics through a concrete transport.

    The transport owns any bounded receive buffer; this base class only
    deserializes the next received byte string.
    """

    def __init__(self, serializer=None):
        if serializer is None:
            from ..serializer.msgpack_serializer import MsgpackSerializer
            serializer = MsgpackSerializer()
        self._serializer = serializer
        self._closed = False

    async def read(self, timeout=None):
        if self._closed:
            raise RuntimeError("reader is closed")
        payload, topic = await self._transport_read(timeout)
        return self._serializer.deserialize(payload), topic

    async def _transport_read(self, timeout):
        raise NotImplementedError

    async def _transport_close(self):
        raise NotImplementedError

    async def close(self):
        if not self._closed:
            self._closed = True
            await self._transport_close()

