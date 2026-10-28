"""MAGPIE image frame with the same wire fields as desktop Python."""

from .frame import Frame


@Frame.register_type
class ImageFrameRaw(Frame):
    """Raw or encoded image bytes and their pixel metadata.

    This class stores the buffer as supplied; it does not encode or decode it.
    """

    def __init__(self, data=b"", format="raw", width=0, height=0,
                 channels=0, pixel_format="", gid=None, id=0, timestamp=None):
        super().__init__(gid=gid, id=id, timestamp=timestamp)
        self.data = data
        self.format = format
        self.width = width
        self.height = height
        self.channels = channels
        self.pixel_format = pixel_format

    def to_dict(self):
        frame = super().to_dict()
        frame["data"] = self.data
        frame["format"] = self.format
        frame["width"] = self.width
        frame["height"] = self.height
        frame["channels"] = self.channels
        frame["pixel_format"] = self.pixel_format
        return frame

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise TypeError("frame must be a dict")
        return cls(
            data=data.get("data", b""),
            format=data.get("format", "raw"),
            width=data.get("width", 0),
            height=data.get("height", 0),
            channels=data.get("channels", 0),
            pixel_format=data.get("pixel_format", ""),
            gid=data.get("gid"),
            id=data.get("id", 0),
            timestamp=data.get("timestamp"),
        )

    def __str__(self):
        dims = "{}x{}x{}".format(self.width, self.height, self.channels) if self.width else "unknown"
        return "{}(size: {}, dims: {}, format: {})".format(
            self.name, len(self.data), dims, self.format)


@Frame.register_type
class ImageFrameJpeg(ImageFrameRaw):
    """JPEG bytes with MAGPIE image metadata; no encoding or decoding."""

    def __init__(self, data=b"", format="jpeg", width=0, height=0,
                 channels=0, pixel_format="", gid=None, id=0, timestamp=None):
        super().__init__(data=data, format=format, width=width, height=height,
                         channels=channels, pixel_format=pixel_format,
                         gid=gid, id=id, timestamp=timestamp)
