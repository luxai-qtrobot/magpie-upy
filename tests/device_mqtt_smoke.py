"""COM13 side of tests/host_mqtt_smoke.py; requires /secrets.py on the board."""

import asyncio
import gc

from secrets import MQTT_CONFIG
from luxai.magpie.frames import IntFrame
from luxai.magpie.schema import McpSchema
from luxai.magpie.transport.mqtt import (
    MqttConnection, MqttStreamReader, MqttStreamWriter, MqttRpcResponder,
)


PREFIX = "luxai/magpie-upy/smoke-com13-20261027"


async def main():
    connection = MqttConnection(MQTT_CONFIG)
    await asyncio.wait_for(connection.connect(), 25)
    reader = MqttStreamReader(connection, PREFIX + "/input")
    writer = MqttStreamWriter(connection)
    raw_rpc = MqttRpcResponder(connection, PREFIX + "/raw")
    schema = McpSchema(name="esp32-smoke")
    schema.register(
        "read_value", lambda: {"value": 42}, description="Read a test value",
        input_schema={"type": "object"}, output_schema={"type": "object"},
    )
    mcp_rpc = MqttRpcResponder(connection, PREFIX + "/mcp", schema=schema)
    try:
        await reader.start()
        await raw_rpc.start()
        await mcp_rpc.start()
        print("device_ready")

        value, _topic = await reader.read(timeout=30)
        assert value == {"from": "desktop", "n": 7}, value
        await writer.write(
            IntFrame(42, gid="S" * 26, id=3, timestamp="123"),
            PREFIX + "/output",
        )

        assert await raw_rpc.respond(
            lambda request: {"from": "esp32", "echo": request}, timeout=30
        )
        for _ in range(3):
            assert await mcp_rpc.respond(timeout=30)
        gc.collect()
        print("free_heap", gc.mem_free())
        print("device_mqtt_smoke_ok")
    finally:
        await reader.close()
        await writer.close()
        await raw_rpc.close()
        await mcp_rpc.close()
        connection.close()


asyncio.run(main())
