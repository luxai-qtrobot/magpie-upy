"""Transport-independent asynchronous stream writer."""

class StreamWriter:
    """Write values to topics through a concrete transport.

    Serialization belongs here; subclasses only send bytes. No worker task or
    queue is created by this base class.
    """

    def __init__(self, serializer=None):
        if serializer is None:
            from ..serializer.msgpack_serializer import MsgpackSerializer
            serializer = MsgpackSerializer()
        self._serializer = serializer
        self._closed = False

    async def write(self, data, topic):
        if self._closed:
            raise RuntimeError("writer is closed")
        if not topic:
            raise ValueError("topic is required")
        await self._transport_write(self._serializer.serialize(data), topic)

    async def _transport_write(self, payload, topic):
        raise NotImplementedError

    async def _transport_close(self):
        raise NotImplementedError

    async def close(self):
        if not self._closed:
            self._closed = True
            await self._transport_close()

