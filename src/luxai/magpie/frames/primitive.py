"""Primitive MAGPIE frames. All have the same on-wire value field."""

from .frame import Frame, _ValueFrame, _MISSING


@Frame.register_type
class BoolFrame(_ValueFrame):
    _default = False


@Frame.register_type
class IntFrame(_ValueFrame):
    _default = 0


@Frame.register_type
class FloatFrame(_ValueFrame):
    _default = 0.0


@Frame.register_type
class StringFrame(_ValueFrame):
    _default = ""


@Frame.register_type
class BytesFrame(_ValueFrame):
    _default = b""

    def __init__(self, value=b"", gid=None, id=0, timestamp=None):
        if isinstance(value, (bytearray, memoryview, list, tuple)):
            value = bytes(value)
        super().__init__(value=value, gid=gid, id=id, timestamp=timestamp)


@Frame.register_type
class DictFrame(_ValueFrame):
    _default = dict

    def __init__(self, value=_MISSING, gid=None, id=0, timestamp=None):
        if value is _MISSING:
            value = {}
        elif not isinstance(value, dict):
            value = dict(value)
        super().__init__(value=value, gid=gid, id=id, timestamp=timestamp)


@Frame.register_type
class ListFrame(_ValueFrame):
    _default = list

    def __init__(self, value=_MISSING, gid=None, id=0, timestamp=None):
        if value is _MISSING:
            value = []
        elif not isinstance(value, list):
            value = list(value)
        super().__init__(value=value, gid=gid, id=id, timestamp=timestamp)


