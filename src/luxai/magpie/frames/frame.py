"""Small, transport-independent MAGPIE frame envelope."""

import os
import time


_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_EPOCH_OFFSET = 946684800 if time.gmtime(0)[0] == 2000 else 0
_MISSING = object()


def _new_gid():
    # A random, 26-character Crockford Base32 ID. MAGPIE treats gid as an
    # opaque string; a valid RTC is not needed for uniqueness after reboot.
    value = 0
    for byte in os.urandom(16):
        value = (value << 8) | byte
    chars = ["0"] * 26
    for index in range(25, -1, -1):
        chars[index] = _ALPHABET[value & 31]
        value >>= 5
    return "".join(chars)


def _timestamp():
    seconds = time.time() + _EPOCH_OFFSET
    # ESP32 often starts at 2000-01-01 until its RTC is synchronised.
    return str(seconds) if seconds >= 1600000000 else "0"


class Frame:
    """MAGPIE frame metadata. Payload subclasses add a value field."""

    _registry = {}

    def __init__(self, gid=None, id=0, timestamp=None):
        self.gid = gid if gid else _new_gid()
        self.id = id if id is not None else 0
        self.name = self.__class__.__name__
        self.timestamp = _timestamp() if timestamp is None else str(timestamp)

    def to_dict(self):
        return {
            "gid": self.gid,
            "id": self.id,
            "name": self.name,
            "timestamp": self.timestamp,
        }

    @classmethod
    def register_type(cls, frame_type):
        """Register a payload frame class for Frame.from_dict."""
        Frame._registry[frame_type.__name__] = frame_type
        return frame_type

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise TypeError("frame must be a dict")
        name = data.get("name")
        frame_type = (
            Frame._registry.get(name, Frame)
            if cls is Frame and isinstance(name, str) else cls
        )
        gid = data.get("gid")
        frame_id = data.get("id", 0)
        timestamp = data.get("timestamp")
        if frame_type is Frame:
            frame = Frame(gid=gid, id=frame_id, timestamp=timestamp)
            if isinstance(name, str):
                frame.name = name
            return frame
        if cls is Frame:
            return frame_type.from_dict(data)
        return frame_type(
            value=data.get("value", _MISSING),
            gid=gid,
            id=frame_id,
            timestamp=timestamp,
        )

    def __str__(self):
        return "{}#{}:{}".format(self.name, self.gid, self.id)


class _ValueFrame(Frame):
    _default = None

    def __init__(self, value=_MISSING, gid=None, id=0, timestamp=None):
        super().__init__(gid=gid, id=id, timestamp=timestamp)
        if value is _MISSING:
            default = self._default
            value = default() if default is dict or default is list else default
        self.value = value

    def to_dict(self):
        data = super().to_dict()
        data["value"] = self.value
        return data


