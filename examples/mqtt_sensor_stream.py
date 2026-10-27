"""Publish a small MAGPIE stream from an ESP32."""

import asyncio
import gc
import network

from luxai.magpie.transport.mqtt import MqttConnection, MqttStreamWriter
from luxai.magpie.utils import Logger


DEVICE_ID = "esp32-001"  # Use a distinct ID for every board.

MQTT_CONFIG = {
    "ssid": "YOUR_WIFI",
    "wifi_pw": "YOUR_WIFI_PASSWORD",
    "server": "broker.hivemq.com",
    "port": 1883,
    "client_id": b"magpie-upy-esp32-001",  # Must be unique on the broker.
}


async def main():
    wifi = network.WLAN(network.STA_IF)
    conn = MqttConnection(MQTT_CONFIG)
    writer = MqttStreamWriter(conn)
    topic = f"magpie-upy/{DEVICE_ID}/sensor"
    try:
        Logger.info(f"Connecting to Wi-Fi: {MQTT_CONFIG.get('ssid')}")
        Logger.info(f"MQTT broker: {MQTT_CONFIG.get('server')}:{MQTT_CONFIG.get('port', 1883)}")
        await conn.connect()
        Logger.info(f"Connected; Wi-Fi: {wifi.isconnected()}, IP: {wifi.ifconfig()[0]}")
        count = 0
        while True:
            reading = {"count": count, "free_heap": gc.mem_free()}
            await writer.write(reading, topic)
            Logger.info(f"{topic} {reading}")
            count += 1
            await asyncio.sleep(2)
    except Exception as error:
        Logger.error(f"Connection or publish failed: {repr(error)}")
        Logger.error(f"Wi-Fi at failure: {wifi.isconnected()} {wifi.ifconfig()}")
        raise
    finally:
        await writer.close()
        conn.close()


asyncio.run(main())

