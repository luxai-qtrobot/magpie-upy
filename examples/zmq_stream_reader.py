"""Read a desktop MAGPIE stream through a direct ZMQ SUB connection."""

import asyncio
import network

from luxai.magpie.transport.zmq import ZmqStreamReader
from luxai.magpie.utils import Logger


DEVICE_ID = "esp32-001"
WIFI_SSID = "YOUR_WIFI"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"
PORT = 5557


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
    topic = f"magpie-upy/{DEVICE_ID}/command"
    reader = ZmqStreamReader(f"tcp://*:{PORT}", topic=topic, bind=True,
                             queue_size=4, delivery="latest")
    try:
        await reader.start()
        Logger.info(f"Reading {topic} on tcp://{board_ip}:{PORT}")
        while True:
            value, received_topic = await reader.read()
            Logger.info(f"{received_topic} {value}")
    finally:
        await reader.close()


asyncio.run(main())
