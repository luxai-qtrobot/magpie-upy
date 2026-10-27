"""MCP tool discovery and invocation over MAGPIE RPC."""

import json

from .json_rpc_schema import JsonRpcSchema, _resolve

MCP_PROTOCOL_VERSION = "2024-11-05"

_BUILTINS = (
    "initialize", "notifications/initialized", "notifications/cancelled",
    "ping", "tools/list", "tools/call",
)


class McpSchema(JsonRpcSchema):
    """Expose registered RPC methods as MCP tools.

    Tool metadata is explicit, with no annotation reflection or JSON Schema
    engine. A desktop MAGPIE MCP adapter provides the standard MCP transport.
    """

    def __init__(self, name="magpie", version="1.0.0"):
        super().__init__()
        self._server_name = name
        self._server_version = version
        register = super().register
        register("initialize", self._initialize)
        register("notifications/initialized", self._notification)
        register("notifications/cancelled", self._notification)
        register("ping", self._ping)
        register("tools/list", self._list_tools)
        register("tools/call", self._call_tool)

    def register(self, name, func=None, description=None,
                 input_schema=None, output_schema=None):
        if name in _BUILTINS:
            raise ValueError("reserved MCP method: " + name)
        super().register(name, func, description, input_schema, output_schema)

    @classmethod
    def from_json(cls, data, **kwargs):
        if isinstance(data, dict):
            data = data.get("tools", [])
        return super().from_json(data, **kwargs)

    def _initialize(self, **_kwargs):
        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": self._server_name,
                "version": self._server_version,
            },
        }

    def _notification(self, **_kwargs):
        return None

    def _ping(self, **_kwargs):
        return {}

    def _list_tools(self, **_kwargs):
        tools = []
        for name, meta in self._methods.items():
            if name in _BUILTINS:
                continue
            tool = {
                "name": name,
                "description": meta["description"],
                "inputSchema": meta["input_schema"],
            }
            output_schema = meta["output_schema"]
            if isinstance(output_schema, dict) and output_schema.get("type") == "object":
                tool["outputSchema"] = output_schema
            tools.append(tool)
        return {"tools": tools}

    async def _call_tool(self, name=None, arguments=None, **_kwargs):
        if not name:
            raise ValueError("'name' is required")
        entry = self._methods.get(name)
        if name in _BUILTINS or entry is None or entry["func"] is None:
            return {"content": [{"type": "text", "text": "Unknown tool: " + str(name)}],
                    "isError": True}
        try:
            result = await _resolve(entry["func"](**(arguments or {})))
            if isinstance(result, (dict, list)):
                text = json.dumps(result)
            else:
                text = str(result)
            response = {"content": [{"type": "text", "text": text}],
                        "isError": False}
            output_schema = entry["output_schema"]
            if (isinstance(result, dict) and isinstance(output_schema, dict)
                    and output_schema.get("type") == "object"):
                response["structuredContent"] = result
            return response
        except Exception as error:
            return {"content": [{"type": "text", "text": str(error)}],
                    "isError": True}

