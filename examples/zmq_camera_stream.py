"""Stream the XIAO ESP32-S3 Sense camera to desktop MAGPIE over ZMQ.

Run this on the board, then on the computer:
    magpie-video-viewer tcp://BOARD_IP:5559 magpie-upy/esp32-001/camera
"""

import asyncio
import gc
import network

from camera import Camera, FrameSize, PixelFormat
from luxai.magpie.frames import ImageFrameJpeg
from luxai.magpie.transport.zmq import ZmqStreamWriter
from luxai.magpie.utils import Logger


DEVICE_ID = "esp32-001"
WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"
PORT = 5559
FRAME_SIZE = FrameSize.VGA  # 640x480 pixels
FRAME_INTERVAL = 0.03  # Give the async sender time between captures.


async def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        for _ in range(100):
            if wlan.isconnected():
                break
            await asyncio.sleep(0.2)
        else:
            raise OSError("Wi-Fi connection timed out")
    board_ip = wlan.ifconfig()[0]
    Logger.info(f"Wi-Fi connected: {board_ip}")
    return board_ip


async def main():
    board_ip = await connect_wifi()
    cam = Camera(pixel_format=PixelFormat.JPEG, frame_size=FRAME_SIZE,
                 init=False)
    cam.init()
    cam.contrast = 2
    width, height = cam.pixel_width, cam.pixel_height
    topic = f"magpie-upy/{DEVICE_ID}/camera"
    writer = ZmqStreamWriter(
        f"tcp://*:{PORT}", queue_size=0, delivery="latest",
        max_message_size=width * height * 2 + 1024,
    )
    try:
        await writer.start()
        Logger.info(f"Camera {cam.sensor_name}: {width}x{height} JPEG")
        Logger.info(f"View {topic} at tcp://{board_ip}:{PORT}")
        Logger.info("Waiting for a viewer...")
        await writer.wait_connected()
        gid = None
        frame_id = 0
        while True:
            raw = cam.capture()
            try:
                jpeg = bytes(raw)
            finally:
                del raw
                cam.free_buffer()
            frame = ImageFrameJpeg(
                data=jpeg, width=width, height=height,
                channels=3, pixel_format="RGB", gid=gid, id=frame_id,
            )
            gid = frame.gid
            await writer.write(frame, topic)
            if frame_id % 10 == 0:
                Logger.info(f"Queued frame {frame_id}: {len(jpeg)} bytes, dropped={writer.dropped}")
            frame_id += 1
            del frame, jpeg
            if frame_id % 10 == 0:
                gc.collect()
            await asyncio.sleep(FRAME_INTERVAL)
    finally:
        await writer.close()
        cam.deinit()


asyncio.run(main())
