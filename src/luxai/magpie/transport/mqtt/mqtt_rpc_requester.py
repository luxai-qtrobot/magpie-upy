"""MAGPIE RPC requester over a shared MQTT connection."""

import asyncio

from ..rpc_requester import RpcRequester, AckTimeoutError, ReplyTimeoutError
from .mqtt_connection import _hex_random


class _Pending:
    def __init__(self):
        self.ack = asyncio.Event()
        self.done = asyncio.Event()
        self.payload = None
        self.error = None


class MqttRpcRequester(RpcRequester):
    """Call a service using MAGPIE's request, ACK, and final-reply envelope.

    A QoS 1 publish can pause during a network outage until mqtt_as reconnects.
    The call timeout covers the ACK and reply waits after publishing, not that
    earlier outage delay. ``max_pending`` caps memory while calls are paused.
    """

    def __init__(self, connection, service_name, serializer=None, schema=None,
                 ack_timeout=2, reply_timeout=10, max_pending=4, qos=1):
        if not service_name or max_pending < 1:
            raise ValueError("service_name and positive max_pending are required")
        super().__init__(schema=schema)
        if serializer is None:
            from ...serializer.msgpack_serializer import MsgpackSerializer
            serializer = MsgpackSerializer()
        self._serializer = serializer
        self._connection = connection
        self._req_topic = service_name.lstrip("/") + "/rpc/req"
        self._instance_id = _hex_random()
        self._rep_topic = "magpie/rpc/%s/%s/rep" % (connection.client_id, self._instance_id)
        self._ack_timeout = ack_timeout
        self._reply_timeout = reply_timeout
        self._max_pending = max_pending
        self._qos = qos
        self._pending = {}
        self._next_id = 0
        self._callback = self._on_reply
        self._started = False

    async def start(self):
        if self._closed:
            raise RuntimeError("requester is closed")
        if not self._started:
            await self._connection.add_subscription(self._rep_topic, self._callback, self._qos)
            self._started = True
        return self

    def _on_reply(self, payload, topic):
        try:
            message = self._serializer.deserialize(payload)
        except Exception:
            return
        if not isinstance(message, dict):
            return
        pending = self._pending.get(message.get("rid"))
        if pending is None:
            return
        if message.get("ack") is True:
            pending.ack.set()
        elif "payload" in message:
            pending.payload = message["payload"]
            pending.ack.set()
            pending.done.set()

    async def _transport_call(self, request_obj, timeout):
        await self.start()
        if len(self._pending) >= self._max_pending:
            raise RuntimeError("too many MQTT RPC calls in progress")
        if timeout is None:
            timeout = self._reply_timeout
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._next_id += 1
        rid = "%s-%x" % (self._instance_id, self._next_id)
        pending = _Pending()
        self._pending[rid] = pending  # register before publishing
        try:
            request = {"rid": rid, "reply_to": self._rep_topic, "payload": request_obj}
            await self._connection.publish(
                self._req_topic, self._serializer.serialize(request), qos=self._qos
            )
            try:
                await asyncio.wait_for(pending.ack.wait(), min(self._ack_timeout, timeout))
            except asyncio.TimeoutError:
                raise AckTimeoutError("no ACK from %s" % self._req_topic)
            if pending.error is not None:
                raise pending.error
            try:
                await asyncio.wait_for(pending.done.wait(), timeout)
            except asyncio.TimeoutError:
                raise ReplyTimeoutError("no reply from %s" % self._req_topic)
            if pending.error is not None:
                raise pending.error
            return pending.payload
        finally:
            self._pending.pop(rid, None)

    async def _transport_close(self):
        if self._started:
            await self._connection.remove_subscription(self._rep_topic, self._callback)
            self._started = False
        for pending in self._pending.values():
            pending.error = RuntimeError("requester is closed")
            pending.ack.set()
            pending.done.set()
        self._pending.clear()

