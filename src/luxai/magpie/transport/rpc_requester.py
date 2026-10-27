"""Transport-independent asynchronous RPC requester."""

try:
    TimeoutError
except NameError:  # MicroPython does not expose it as a built-in.
    from asyncio import TimeoutError


class AckTimeoutError(TimeoutError):
    """The responder did not acknowledge the request."""


class ReplyTimeoutError(TimeoutError):
    """The responder acknowledged but did not complete the request."""


class RpcRequester:
    """Call a service through a concrete transport.

    With a schema, a string request is a method name and keyword arguments
    become its parameters. Other requests pass through unchanged.
    """

    def __init__(self, schema=None):
        self._schema = schema
        self._closed = False

    async def call(self, request_obj, timeout=None, **params):
        if self._closed:
            raise RuntimeError("requester is closed")
        if self._schema is not None and isinstance(request_obj, str):
            timeout = params.pop("_timeout", timeout)
            request_obj = self._schema.wrap(request_obj, params or None)
            response = await self._transport_call(request_obj, timeout)
            return self._schema.unwrap(response)
        if params:
            raise TypeError("keyword parameters require a schema and method name")
        return await self._transport_call(request_obj, timeout)

    async def _transport_call(self, request_obj, timeout):
        raise NotImplementedError

    async def _transport_close(self):
        raise NotImplementedError

    async def close(self):
        if not self._closed:
            self._closed = True
            await self._transport_close()

