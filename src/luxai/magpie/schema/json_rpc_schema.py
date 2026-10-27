"""Small JSON-RPC 2.0 schema for MAGPIE RPC.

Method descriptions and input/output schemas are supplied explicitly. This
avoids CPython's inspect and type-hint machinery on MicroPython.
"""

from .base_schema import BaseSchema

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class JsonRpcError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


async def _resolve(value):
    # MicroPython coroutine objects expose send() but not always __await__.
    if hasattr(value, "__await__") or hasattr(value, "send"):
        return await value
    return value


class JsonRpcSchema(BaseSchema):
    def __init__(self):
        self._methods = {}
        self._next_id = 1

    def register(self, name, func=None, description=None,
                 input_schema=None, output_schema=None):
        if not name:
            raise ValueError("method name is required")
        self._methods[name] = {
            "func": func,
            "description": description or "",
            "input_schema": input_schema if input_schema is not None else {"type": "object"},
            "output_schema": output_schema,
        }

    def method(self, name=None, description=None, input_schema=None,
               output_schema=None):
        def decorator(func):
            self.register(name or func.__name__, func, description,
                          input_schema, output_schema)
            return func
        return decorator

    def handler(self, name):
        def decorator(func):
            if name not in self._methods:
                raise KeyError(name)
            self._methods[name]["func"] = func
            return func
        return decorator

    @classmethod
    def from_json(cls, data, **kwargs):
        if not isinstance(data, list):
            raise ValueError("expected a list of methods")
        schema = cls(**kwargs)
        for item in data:
            schema.register(item["name"], description=item.get("description"),
                            input_schema=item.get("inputSchema"),
                            output_schema=item.get("outputSchema"))
        return schema

    def wrap(self, method, params=None):
        request = {"jsonrpc": "2.0", "method": method, "id": self._next_id}
        self._next_id += 1
        if params:
            request["params"] = params
        return request

    def unwrap(self, response):
        if not isinstance(response, dict):
            raise JsonRpcError(INVALID_REQUEST, "invalid JSON-RPC response")
        if "error" in response:
            error = response["error"]
            if not isinstance(error, dict):
                raise JsonRpcError(INTERNAL_ERROR, "invalid JSON-RPC error")
            raise JsonRpcError(error.get("code", INTERNAL_ERROR),
                               error.get("message", "unknown error"))
        return response.get("result")

    def _error(self, req_id, code, message):
        return {"jsonrpc": "2.0", "error": {"code": code, "message": message},
                "id": req_id}

    async def _dispatch_single(self, request):
        if not isinstance(request, dict):
            return self._error(None, INVALID_REQUEST, "Request must be an object")
        req_id = request.get("id")
        method = request.get("method")
        if not method:
            return self._error(req_id, INVALID_REQUEST, "Missing 'method' field")
        entry = self._methods.get(method)
        if entry is None or entry["func"] is None:
            if req_id is None:
                return None
            return self._error(req_id, METHOD_NOT_FOUND,
                               "Method not found: " + str(method))
        params = request.get("params")
        try:
            if params is None:
                result = entry["func"]()
            elif isinstance(params, dict):
                result = entry["func"](**params)
            elif isinstance(params, list):
                result = entry["func"](*params)
            else:
                return self._error(req_id, INVALID_PARAMS,
                                   "'params' must be object or array")
            result = await _resolve(result)
        except TypeError as error:
            if req_id is None:
                return None
            return self._error(req_id, INVALID_PARAMS, str(error))
        except Exception as error:
            if req_id is None:
                return None
            return self._error(req_id, INTERNAL_ERROR, str(error))
        if req_id is None:
            return None
        return {"jsonrpc": "2.0", "result": result, "id": req_id}

    async def dispatch(self, request_obj):
        if isinstance(request_obj, list):
            if not request_obj:
                return self._error(None, INVALID_REQUEST, "Empty batch")
            replies = []
            for request in request_obj:
                reply = await self._dispatch_single(request)
                if reply is not None:
                    replies.append(reply)
            return replies or None
        return await self._dispatch_single(request_obj)

