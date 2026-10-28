"""Serve a MAGPIE MCP tool from a board over a local ZMQ ROUTER socket."""

import asyncio
import gc
import network

from luxai.magpie.schema import McpSchema
from luxai.magpie.transport.zmq import ZmqRpcResponder
from luxai.magpie.utils import Logger


DEVICE_ID = "esp32-001"
WIFI_SSID = "YOUR_WIFI"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"
PORT = 5556


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
    Logger.info(f"Wi-Fi connected: {wlan.ifconfig()[0]}")
    return wlan.ifconfig()[0]


def free_memory():
    return {"bytes": gc.mem_free()}


async def main():
    board_ip = await connect_wifi()
    schema = McpSchema(name=DEVICE_ID)
    schema.register(
        "free_memory", free_memory,
        description="Return the board's free heap in bytes.",
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object", "properties": {
            "bytes": {"type": "integer"}}, "required": ["bytes"]},
    )
    responder = ZmqRpcResponder(f"tcp://*:{PORT}", schema=schema)
    try:
        await responder.start()
        Logger.info(f"Serving MCP tools on tcp://{board_ip}:{PORT}")
        while True:
            await responder.respond(timeout=1)
    finally:
        await responder.close()


asyncio.run(main())
