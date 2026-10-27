"""ESP32 requester against tests/host_responder_smoke.py."""

import asyncio

from secrets import MQTT_CONFIG
from luxai.magpie.transport.mqtt import MqttConnection, MqttRpcRequester


SERVICE = "luxai/magpie-upy/smoke-com13-20261027/desktop"


async def main():
    connection = MqttConnection(MQTT_CONFIG)
    requester = MqttRpcRequester(connection, SERVICE)
    try:
        await asyncio.wait_for(connection.connect(), 25)
        reply = await requester.call({"from": "esp32", "n": 11}, timeout=12)
        assert reply == {"from": "desktop", "n": 12}, reply
        print("device_requester_smoke_ok")
    finally:
        await requester.close()
        connection.close()


asyncio.run(main())
