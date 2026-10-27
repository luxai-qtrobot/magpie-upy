"""Transport-independent serializer contract."""


class BaseSerializer:
    def serialize(self, data):
        raise NotImplementedError

    def deserialize(self, data):
        raise NotImplementedError


