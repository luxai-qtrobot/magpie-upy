"""Host-side MQTT wire tests with a small in-memory broker (no Wi-Fi needed)."""

import asyncio
import sys
import unittest
from pathlib import Path

import msgpack

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from luxai.magpie.frames import Frame, IntFrame
from luxai.magpie.transport.mqtt import (
    MqttConnection, MqttRpcRequester, MqttRpcResponder,
    MqttStreamReader, MqttStreamWriter,
)
from luxai.magpie.transport.mqtt.mqtt_connection import _matches
from luxai.magpie.transport.rpc_requester import AckTimeoutError


class _Msgpack:
    def serialize(self, value):
        if hasattr(value, "to_dict"):
            value = value.to_dict()
        return msgpack.packb(value)

    def deserialize(self, payload):
        return msgpack.unpackb(payload)


class _Broker:
    def __init__(self):
        self.clients = []
        self.sent = []

    def client(self):
        client = _Client(self)
        self.clients.append(client)
        return client

    def deliver(self, topic, payload):
        for client in self.clients:
            if any(_matches(pattern, topic) for pattern in client.subscriptions):
                # Match mqtt_as's bytes topic / bytearray payload callback shape.
                client.config["subs_cb"](topic.encode(), bytearray(payload), False)


class _Client:
    def __init__(self, broker):
        self.broker = broker
        self.config = None
        self.subscriptions = {}

    async def connect(self):
        await self.config["connect_coro"](self)

    async def subscribe(self, topic, qos):
        self.subscriptions[topic] = qos

    async def unsubscribe(self, topic):
        self.subscriptions.pop(topic, None)

    async def publish(self, topic, payload, qos=0, retain=False):
        self.broker.sent.append((topic, bytes(payload), qos))
        self.broker.deliver(topic, payload)

    def close(self):
        pass


def _connection(broker, client_id):
    client = broker.client()
    connection = MqttConnection({"client_id": client_id}, client=client)
    client.config = connection.config
    return connection, client


class MqttWireTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_raw_frame_and_latest_buffer(self):
        broker = _Broker()
        source, _ = _connection(broker, "source")
        sink, sink_client = _connection(broker, "sink")
        await source.connect()
        await sink.connect()
        writer = MqttStreamWriter(source, serializer=_Msgpack())
        reader = MqttStreamReader(sink, "sensor/+", serializer=_Msgpack(), queue_size=1)
        await reader.start()

        await writer.write({"count": 1}, "sensor/temp")
        await writer.write(IntFrame(42, gid="fixed-gid", id=3, timestamp="123.5"), "sensor/temp")
        value, topic = await reader.read(timeout=1)
        self.assertEqual(topic, "sensor/temp")
        self.assertEqual(reader.dropped, 1)
        self.assertEqual(value, {"gid": "fixed-gid", "id": 3,
                                 "name": "IntFrame", "timestamp": "123.5", "value": 42})
        self.assertEqual(Frame.from_dict(value).value, 42)
        self.assertEqual(sink_client.subscriptions["sensor/+"], 1)

        # mqtt_as invokes connect_coro after an outage; subscriptions persist.
        sink_client.subscriptions.clear()
        await sink._on_connect(sink_client)
        self.assertEqual(sink_client.subscriptions["sensor/+"], 1)
        await reader.close()
        await writer.close()
        source.close()
        sink.close()

    async def test_rpc_ack_final_reply_and_duplicate_request(self):
        broker = _Broker()
        caller, _ = _connection(broker, "caller")
        server, _ = _connection(broker, "server")
        await caller.connect()
        await server.connect()
        requester = MqttRpcRequester(caller, "/motor", serializer=_Msgpack())
        responder = MqttRpcResponder(server, "motor", serializer=_Msgpack())
        await responder.start()
        handled = []

        def move(request):
            handled.append(request["position"])
            return {"ok": True}

        task = asyncio.create_task(requester.call({"position": 3}, timeout=1))
        self.assertTrue(await responder.respond(move, timeout=1))
        self.assertEqual(await task, {"ok": True})
        request_topic, request_bytes, request_qos = next(
            item for item in broker.sent if item[0] == "motor/rpc/req"
        )
        self.assertEqual(request_qos, 1)
        request = msgpack.unpackb(request_bytes)
        self.assertEqual(request["payload"], {"position": 3})
        replies = [msgpack.unpackb(data) for topic, data, _ in broker.sent
                   if topic == request["reply_to"]]
        self.assertEqual(replies, [
            {"rid": request["rid"], "ack": True},
            {"rid": request["rid"], "payload": {"ok": True}},
        ])

        # Re-delivery of the same QoS 1 request replays the cached reply.
        broker.deliver(request_topic, request_bytes)
        self.assertFalse(await responder.respond(move, timeout=0.01))
        self.assertEqual(handled, [3])
        await requester.close()
        await responder.close()
        caller.close()
        server.close()

    async def test_rpc_ack_timeout_and_bounded_request_queue(self):
        broker = _Broker()
        caller, _ = _connection(broker, "caller")
        server, _ = _connection(broker, "server")
        await caller.connect()
        await server.connect()
        requester = MqttRpcRequester(caller, "missing", serializer=_Msgpack(), ack_timeout=0.01)
        with self.assertRaises(AckTimeoutError):
            await requester.call({"x": 1}, timeout=0.1)
        self.assertEqual(len(requester._pending), 0)

        responder = MqttRpcResponder(server, "full", serializer=_Msgpack(), queue_size=1)
        await responder.start()
        envelope = {"rid": "a", "reply_to": "reply", "payload": {"x": 1}}
        broker.deliver("full/rpc/req", msgpack.packb(envelope))
        envelope["rid"] = "b"
        broker.deliver("full/rpc/req", msgpack.packb(envelope))
        self.assertEqual(responder.dropped, 1)
        self.assertEqual(await responder.respond(lambda x: x, timeout=1), True)
        await requester.close()
        await responder.close()
        caller.close()
        server.close()


if __name__ == "__main__":
    unittest.main()
