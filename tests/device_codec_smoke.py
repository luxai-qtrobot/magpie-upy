"""Run with: mpremote connect COM13 run tests/device_codec_smoke.py.

Requires the package installed on the board. No Wi-Fi or broker is used.
"""

import binascii
import gc
import umsgpack

from luxai.magpie.frames import Frame, IntFrame
from luxai.magpie.serializer import MsgpackSerializer


gc.collect()
before = gc.mem_free()

# Produced by desktop Python's msgpack.packb(..., use_bin_type=True).
desktop_hex = "82a46e616d65a75154726f626f74a576616c75652a"
desktop_value = umsgpack.loads(binascii.unhexlify(desktop_hex))
assert desktop_value == {"name": "QTrobot", "value": 42}

serializer = MsgpackSerializer()
raw = {"name": "QTrobot", "value": 42, "binary": b"\x00\xff"}
raw_wire = serializer.serialize(raw)
assert serializer.deserialize(raw_wire) == raw

frame = IntFrame(42, gid="0" * 26, id=7, timestamp="123.25")
frame_wire = serializer.serialize(frame)
decoded_frame = serializer.deserialize(frame_wire)
assert Frame.from_dict(decoded_frame).to_dict() == frame.to_dict()

gc.collect()
print("raw_hex", binascii.hexlify(raw_wire).decode())
print("frame_hex", binascii.hexlify(frame_wire).decode())
print("free_heap_before", before)
print("free_heap_after", gc.mem_free())
print("codec_smoke_ok")
