"""ESP32 SUB versus desktop PUB, plus an on-device DEALER/ROUTER check."""

import asyncio
import gc
import network

from secrets import MQTT_CONFIG
from luxai.magpie.transport.zmq import (
    ZmqStreamReader, ZmqRpcRequester, ZmqRpcResponder,
)


async def main():
    wifi = network.WLAN(network.STA_IF)
    wifi.active(True)
    if not wifi.isconnected():
        wifi.connect(MQTT_CONFIG["ssid"], MQTT_CONFIG["wifi_pw"])
        for _ in range(100):
            if wifi.isconnected():
                break
            await asyncio.sleep(0.2)
    if not wifi.isconnected():
        raise RuntimeError("Wi-Fi connection timed out")
    reader = ZmqStreamReader("tcp://*:58675", "magpie-upy/zmq/input",
                             bind=True)
    local_responder = ZmqRpcResponder("tcp://127.0.0.1:58676")
    requester = ZmqRpcRequester("tcp://127.0.0.1:58676")
    try:
        await reader.start()
        await local_responder.start()
        await requester.start()
        print("device_zmq_sub_ready", wifi.ifconfig()[0])
        value, topic = await reader.read(timeout=30)
        assert topic == "magpie-upy/zmq/input", topic
        assert value == {"from": "desktop", "n": 7}, value
        call = asyncio.create_task(requester.call({"from": "esp32", "n": 8}, timeout=5))
        assert await local_responder.respond(
            lambda _request: {"from": "desktop", "n": 8}, timeout=5)
        reply = await call
        assert reply == {"from": "desktop", "n": 8}, reply
        gc.collect()
        print("device_zmq_client_ok", gc.mem_free())
    finally:
        await requester.close()
        await local_responder.close()
        await reader.close()


asyncio.run(main())
