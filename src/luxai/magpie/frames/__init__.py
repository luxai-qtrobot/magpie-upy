"""Portable MAGPIE frame types."""

from .frame import Frame
from .primitive import (
    BoolFrame,
    IntFrame,
    FloatFrame,
    StringFrame,
    BytesFrame,
    DictFrame,
    ListFrame,
)
from .image import ImageFrameRaw, ImageFrameJpeg


