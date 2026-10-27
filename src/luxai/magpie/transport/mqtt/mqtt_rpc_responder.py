"""MAGPIE RPC responder over a shared MQTT connection."""

from ..rpc_responder import RpcResponder
from .mqtt_connection import _Mailbox


class MqttRpcResponder(RpcResponder):
    """Serve one request at a time with an immediate ACK and a final reply.

    A small recent-reply cache prevents repeated side effects for common QoS 1
    redeliveries. Handlers should still be idempotent: cache entries expire.
    """

    def __init__(self, connection, service_name, serializer=None, schema=None,
                 queue_size=4, qos=1, recent_limit=4, recent_payload_limit=1024):
        if not service_name or queue_size < 1 or recent_limit < 0:
            raise ValueError("service_name and positive queue_size are required")
        super().__init__(schema=schema)
        if serializer is None:
            from ...serializer.msgpack_serializer import MsgpackSerializer
            serializer = MsgpackSerializer()
        self._serializer = serializer
        self._connection = connection
        self._req_topic = service_name.lstrip("/") + "/rpc/req"
        self._qos = qos
        self._mailbox = _Mailbox(queue_size)
        self._callback = self._on_request
        self._started = False
        self._busy = False
        self._recent = {}  # (rid, reply_to) -> encoded final reply
        self._recent_limit = recent_limit
        self._recent_payload_limit = recent_payload_limit
        self.malformed = 0

    @property
    def dropped(self):
        return self._mailbox.dropped

    def _on_request(self, payload, topic):
        # A full RPC mailbox rejects the request by omitting ACK. The caller
        # then sees an ACK timeout; it must never lose a request silently.
        self._mailbox.put(payload)

    async def start(self):
        if self._closed:
            raise RuntimeError("responder is closed")
        if not self._started:
            await self._connection.add_subscription(self._req_topic, self._callback, self._qos)
            self._started = True
        return self

    async def respond(self, handler=None, timeout=None):
        if self._busy:
            raise RuntimeError("respond() is already active")
        self._busy = True
        try:
            await self.start()
            return await super().respond(handler=handler, timeout=timeout)
        finally:
            self._busy = False

    async def _transport_recv(self, timeout):
        while True:
            payload = await self._mailbox.get(timeout)
            try:
                message = self._serializer.deserialize(payload)
            except Exception:
                self.malformed += 1
                continue
            if not isinstance(message, dict):
                self.malformed += 1
                continue
            rid = message.get("rid")
            reply_to = message.get("reply_to")
            if (not isinstance(rid, str) or not rid or
                    not isinstance(reply_to, str) or not reply_to or
                    "+" in reply_to or "#" in reply_to or
                    "payload" not in message):
                self.malformed += 1
                continue
            context = (rid, reply_to)
            await self._connection.publish(
                reply_to, self._serializer.serialize({"rid": rid, "ack": True}), qos=self._qos
            )
            cached = self._recent.get(context)
            if cached is not None:
                await self._connection.publish(reply_to, cached, qos=self._qos)
                continue
            return message["payload"], context

    async def _transport_send(self, response_obj, context):
        rid, reply_to = context
        encoded = self._serializer.serialize({"rid": rid, "payload": response_obj})
        if self._recent_limit and len(encoded) <= self._recent_payload_limit:
            if len(self._recent) >= self._recent_limit:
                self._recent.pop(next(iter(self._recent)))
            self._recent[context] = encoded
        await self._connection.publish(reply_to, encoded, qos=self._qos)

    async def _transport_close(self):
        if self._started:
            await self._connection.remove_subscription(self._req_topic, self._callback)
            self._started = False
        self._mailbox.close()
        self._recent.clear()

