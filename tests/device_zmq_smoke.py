"""ESP32 side of a desktop MAGPIE ZMQ smoke test; uses /secrets.py Wi-Fi."""

import asyncio
import gc
import network

from secrets import MQTT_CONFIG
from luxai.magpie.schema import McpSchema
from luxai.magpie.transport.zmq import ZmqStreamWriter, ZmqRpcResponder


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

    writer = ZmqStreamWriter("tcp://*:58671")
    schema = McpSchema(name="esp32-zmq-smoke")
    schema.register("free_heap", lambda: {"bytes": gc.mem_free()},
                    input_schema={"type": "object"},
                    output_schema={"type": "object"})
    responder = ZmqRpcResponder("tcp://*:58672", schema=schema)
    await writer.start()
    await responder.start()
    print("device_zmq_ready", wifi.ifconfig()[0], "free_heap", gc.mem_free())
    try:
        for count in range(30):
            await writer.write({"count": count, "blob": "x" * 512},
                               "magpie-upy/zmq/sensor")
            await responder.respond(timeout=0.2)
            await asyncio.sleep(0.8)
    finally:
        await responder.close()
        await writer.close()
        gc.collect()
        print("device_zmq_done", gc.mem_free())


asyncio.run(main())
