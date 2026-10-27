"""Host checks for the small frame envelope and serializer interface."""

import sys
import types
import unittest
from unittest.mock import patch

import msgpack

from luxai.magpie.frames import (
    Frame, BoolFrame, IntFrame, FloatFrame, StringFrame,
    BytesFrame, DictFrame, ListFrame,
)
from luxai.magpie.serializer import MsgpackSerializer


class TestFrames(unittest.TestCase):
    def test_primitive_round_trip_preserves_wire_metadata(self):
        values = (
            (BoolFrame, True),
            (IntFrame, 42),
            (FloatFrame, 1.5),
            (StringFrame, "hello"),
            (BytesFrame, b"\x00\xff"),
            (DictFrame, {"count": 3}),
            (ListFrame, [1, 2]),
        )
        for frame_type, value in values:
            with self.subTest(frame_type=frame_type.__name__):
                frame = frame_type(value, gid="FIXED", id=7, timestamp="123.25")
                wire = frame.to_dict()
                self.assertEqual(wire, {
                    "gid": "FIXED", "id": 7,
                    "name": frame_type.__name__,
                    "timestamp": "123.25", "value": value,
                })
                restored = Frame.from_dict(wire)
                self.assertIs(type(restored), frame_type)
                self.assertEqual(restored.to_dict(), wire)

    def test_generated_ids_and_independent_mutable_defaults(self):
        first = DictFrame()
        second = DictFrame()
        first.value["x"] = 1
        self.assertEqual(second.value, {})
        self.assertEqual(len(first.gid), 26)
        self.assertNotEqual(first.gid, second.gid)
        self.assertIsInstance(first.timestamp, str)

    def test_raw_dictionary_is_not_an_implicit_frame(self):
        self.assertEqual(Frame.from_dict({"x": 1}).to_dict()["name"], "Frame")


class TestSerializer(unittest.TestCase):
    def test_raw_values_and_frame_values(self):
        # CPython msgpack stands in for the umsgpack API. On-device tests use
        # the installed umsgpack implementation itself.
        codec = types.ModuleType("umsgpack")
        codec.dumps = msgpack.packb
        codec.loads = msgpack.unpackb
        with patch.dict(sys.modules, {"umsgpack": codec}):
            serializer = MsgpackSerializer()
        self.assertEqual(serializer.deserialize(serializer.serialize({"v": 1})), {"v": 1})
        wire = serializer.deserialize(
            serializer.serialize(IntFrame(42, gid="FIXED", timestamp="123"))
        )
        self.assertEqual(wire["name"], "IntFrame")
        self.assertEqual(wire["value"], 42)


if __name__ == "__main__":
    unittest.main()
