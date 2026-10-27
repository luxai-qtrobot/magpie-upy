"""Transport-independent asynchronous RPC responder."""

try:
    TimeoutError
except NameError:  # MicroPython does not expose it as a built-in.
    from asyncio import TimeoutError


async def _resolve(value):
    # MicroPython coroutine objects expose send() but not always __await__.
    if hasattr(value, "__await__") or hasattr(value, "send"):
        return await value
    return value


class RpcResponder:
    """Handle one request at a time through a concrete transport."""

    def __init__(self, schema=None):
        self._schema = schema
        self._closed = False

    async def respond(self, handler=None, timeout=None):
        if self._closed:
            raise RuntimeError("responder is closed")
        if handler is None and self._schema is None:
            raise ValueError("handler or schema is required")
        try:
            request_obj, context = await self._transport_recv(timeout)
        except TimeoutError:
            return False
        if self._schema is not None:
            response = await _resolve(self._schema.dispatch(request_obj))
            if response is not None:
                await self._transport_send(response, context)
        else:
            response = await _resolve(handler(request_obj))
            await self._transport_send(response, context)
        return True

    async def _transport_recv(self, timeout):
        raise NotImplementedError

    async def _transport_send(self, response_obj, context):
        raise NotImplementedError

    async def _transport_close(self):
        raise NotImplementedError

    async def close(self):
        if not self._closed:
            self._closed = True
            await self._transport_close()

