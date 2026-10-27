"""Expose an ESP32 free-memory MCP tool through MAGPIE MQTT RPC."""

import asyncio
import gc

from luxai.magpie.schema import McpSchema
from luxai.magpie.transport.mqtt import MqttConnection, MqttRpcResponder
from luxai.magpie.utils import Logger


DEVICE_ID = "esp32-001"  # Use a distinct ID for every board.

MQTT_CONFIG = {
    "ssid": "YOUR_WIFI",
    "wifi_pw": "YOUR_WIFI_PASSWORD",
    "server": "broker.hivemq.com",
    "port": 1883,
    "client_id": b"magpie-upy-esp32-001",  # Must be unique on the broker.
}


def free_memory():
    return {"bytes": gc.mem_free()}


async def main():
    schema = McpSchema(name=DEVICE_ID)
    schema.register(
        "free_memory",
        free_memory,
        description="Return the ESP32 free heap in bytes.",
        input_schema={"type": "object", "properties": {}},
        output_schema={
            "type": "object",
            "properties": {"bytes": {"type": "integer"}},
            "required": ["bytes"],
        },
    )
    conn = MqttConnection(MQTT_CONFIG)
    responder = MqttRpcResponder(conn, service_name=f"{DEVICE_ID}/mcp", schema=schema)
    try:
        await conn.connect()
        await responder.start()
        Logger.info(f"Serving MCP tools on {DEVICE_ID}/mcp")
        while True:
            await responder.respond(timeout=1)
    finally:
        await responder.close()
        conn.close()


asyncio.run(main())

