"""Host checks for transport-independent async APIs and MCP dispatch."""

import unittest

from luxai.magpie.schema import McpSchema
from luxai.magpie.transport import StreamReader, StreamWriter, RpcRequester


class Codec:
    def serialize(self, value):
        return str(value).encode()

    def deserialize(self, value):
        return value.decode()


class Writer(StreamWriter):
    def __init__(self):
        super().__init__(serializer=Codec())
        self.sent = []

    async def _transport_write(self, payload, topic):
        self.sent.append((payload, topic))

    async def _transport_close(self):
        pass


class Reader(StreamReader):
    async def _transport_read(self, timeout):
        return b"sample", "sensor/temp"

    async def _transport_close(self):
        pass


class LocalRequester(RpcRequester):
    def __init__(self, schema):
        super().__init__(schema=schema)

    async def _transport_call(self, request, timeout):
        return await self._schema.dispatch(request)

    async def _transport_close(self):
        pass


class CoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_contract_with_injected_serializer(self):
        writer = Writer()
        reader = Reader(serializer=Codec())
        await writer.write(42, "sensor/temp")
        self.assertEqual(writer.sent, [(b"42", "sensor/temp")])
        self.assertEqual(await reader.read(timeout=1), ("sample", "sensor/temp"))
        await writer.close()
        await reader.close()

    async def test_mcp_tool_discovery_and_call(self):
        schema = McpSchema(name="esp32")

        async def read_pin(pin):
            return {"pin": pin, "value": 1}

        schema.register(
            "read_pin", read_pin, description="Read a digital input",
            input_schema={"type": "object", "properties": {"pin": {"type": "integer"}}},
            output_schema={"type": "object"},
        )
        requester = LocalRequester(schema)
        initialize = await requester.call("initialize")
        self.assertEqual(initialize["serverInfo"]["name"], "esp32")
        tools = await requester.call("tools/list")
        self.assertEqual([tool["name"] for tool in tools["tools"]], ["read_pin"])
        result = await requester.call("tools/call", name="read_pin", arguments={"pin": 4})
        self.assertEqual(result["structuredContent"], {"pin": 4, "value": 1})
        await requester.close()


if __name__ == "__main__":
    unittest.main()
