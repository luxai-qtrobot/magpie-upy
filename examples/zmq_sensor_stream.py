"""Publish a MAGPIE stream to a desktop SUB socket over local TCP."""

import asyncio
import gc
import network

from luxai.magpie.frames import DictFrame
from luxai.magpie.transport.zmq import ZmqStreamWriter
from luxai.magpie.utils import Logger


DEVICE_ID = "esp32-001"
WIFI_SSID = "YOUR_WIFI"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"
PORT = 5555


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
    topic = f"magpie-upy/{DEVICE_ID}/sensor"
    writer = ZmqStreamWriter(f"tcp://*:{PORT}", queue_size=0,
                             delivery="latest")
    try:
        await writer.start()
        Logger.info(f"Publishing {topic} on tcp://{board_ip}:{PORT}")
        count = 0
        gid = None
        while True:
            value = {"count": count, "free_heap": gc.mem_free()}
            frame = DictFrame(value, gid=gid, id=count)
            gid = frame.gid
            await writer.write(frame, topic)
            Logger.info(f"{topic} {value}")
            count += 1
            await asyncio.sleep(2)
    finally:
        await writer.close()


asyncio.run(main())
