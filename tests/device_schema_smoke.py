"""Run with: mpremote connect COM13 run tests/device_schema_smoke.py."""

import asyncio
import gc

from luxai.magpie.schema import McpSchema


async def main():
    gc.collect()
    before = gc.mem_free()
    schema = McpSchema(name="esp32")

    async def read_pin(pin):
        await asyncio.sleep_ms(0)
        return {"pin": pin, "value": 1}

    schema.register(
        "read_pin", read_pin, description="Read input",
        input_schema={"type": "object", "properties": {"pin": {"type": "integer"}}},
        output_schema={"type": "object"},
    )
    init = await schema.dispatch({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init["result"]["serverInfo"]["name"] == "esp32"
    tools = await schema.dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert tools["result"]["tools"][0]["name"] == "read_pin"
    call = await schema.dispatch({
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "read_pin", "arguments": {"pin": 4}},
    })
    assert call["result"]["structuredContent"] == {"pin": 4, "value": 1}
    gc.collect()
    print("free_heap_before", before)
    print("free_heap_after", gc.mem_free())
    print("schema_smoke_ok")


asyncio.run(main())
