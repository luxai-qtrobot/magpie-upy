"""Transport-neutral writer implemented with a shared MQTT connection."""

from ..stream_writer import StreamWriter


class MqttStreamWriter(StreamWriter):
    """Serialize a value and publish it directly; no writer task or queue."""

    def __init__(self, connection, serializer=None, qos=1, retain=False):
        super().__init__(serializer=serializer)
        self._connection = connection
        self._qos = qos
        self._retain = retain

    async def _transport_write(self, payload, topic):
        await self._connection.publish(topic, payload, qos=self._qos, retain=self._retain)

    async def _transport_close(self):
        # The connection is shared and belongs to its creator.
        pass

