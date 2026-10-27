"""Bounded MQTT stream reader."""

from ..stream_reader import StreamReader
from .mqtt_connection import _Mailbox


class MqttStreamReader(StreamReader):
    """Read one subscribed topic (including MQTT +/# wildcard patterns).

    Call ``await start()`` before the publisher starts to avoid missing early
    messages. ``read()`` calls start lazily as a convenience.
    """

    def __init__(self, connection, topic, serializer=None, queue_size=4, qos=1):
        if not topic:
            raise ValueError("topic is required")
        super().__init__(serializer=serializer)
        self._connection = connection
        self._topic = topic
        self._qos = qos
        self._mailbox = _Mailbox(queue_size, drop_oldest=True)
        self._callback = self._on_message
        self._started = False

    @property
    def dropped(self):
        return self._mailbox.dropped

    def _on_message(self, payload, topic):
        self._mailbox.put((payload, topic))

    async def start(self):
        if self._closed:
            raise RuntimeError("reader is closed")
        if not self._started:
            await self._connection.add_subscription(self._topic, self._callback, self._qos)
            self._started = True
        return self

    async def _transport_read(self, timeout):
        await self.start()
        return await self._mailbox.get(timeout)

    async def _transport_close(self):
        if self._started:
            await self._connection.remove_subscription(self._topic, self._callback)
            self._started = False
        self._mailbox.close()

