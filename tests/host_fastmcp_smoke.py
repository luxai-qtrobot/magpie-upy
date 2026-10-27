"""Desktop FastMCP client against examples/mqtt_mcp_tool.py on COM13."""

import asyncio

from fastmcp import Client

from luxai.magpie.adapters.mcp import McpTransport
from luxai.magpie.transport.mqtt import MqttConnection, MqttRpcRequester


async def main():
    connection = MqttConnection(
        "mqtt://broker.hivemq.com:1883", protocol_version=3,
    )
    connection.connect(timeout=10)
    requester = MqttRpcRequester(connection, service_name="esp32-001/mcp")
    try:
        async with Client(McpTransport(requester, timeout=15)) as client:
            tools = await client.list_tools()
            assert [tool.name for tool in tools] == ["free_memory"]
            result = await client.call_tool("free_memory", {})
            assert not result.is_error
            assert int(result.structured_content["bytes"]) > 0
            print("host_fastmcp_smoke_ok")
    finally:
        requester.close()
        connection.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
