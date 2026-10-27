"""MessagePack adapter for the MicroPython umsgpack package."""

from .base_serializer import BaseSerializer


class MsgpackSerializer(BaseSerializer):
    def __init__(self):
        import umsgpack
        self._codec = umsgpack

    def serialize(self, data):
        # Streams also accept raw dict/list/scalar values; Frame is optional.
        if hasattr(data, "to_dict"):
            data = data.to_dict()
        return self._codec.dumps(data)

    def deserialize(self, data):
        return self._codec.loads(data)


