"""Host interoperability checks against real libzmq sockets.

Run with a Python environment containing ``pyzmq`` and ``msgpack``. These
tests exercise the same TCP wire paths used by desktop MAGPIE while importing
the MicroPython transport directly from this repository.
"""

import asyncio
import socket
import sys
import unittest
from pathlib import Path

import msgpack

if sys.platform == "win32":
    # pyzmq's asyncio sockets need a selector loop on Windows.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

try:
    import zmq
    import zmq.asyncio
except ImportError:
    zmq = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from luxai.magpie.schema import McpSchema
from luxai.magpie.frames import DictFrame
from luxai.magpie.transport.zmq import (
    ZmqRpcRequester, ZmqRpcResponder, ZmqStreamReader, ZmqStreamWriter,
)


class _Msgpack:
    def serialize(self, value):
        if hasattr(value, "to_dict"):
            value = value.to_dict()
        return msgpack.packb(value, use_bin_type=True)

    def deserialize(self, payload):
        return msgpack.unpackb(payload, raw=False)


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@unittest.skipUnless(zmq is not None, "pyzmq is needed for ZMQ interoperability tests")
class ZmqInteropTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.context = zmq.asyncio.Context()
        self.sockets = []
        self.codec = _Msgpack()

    async def asyncTearDown(self):
        for peer in self.sockets:
            peer.close(linger=0)
        self.context.destroy(linger=0)

    def _host_socket(self, kind):
        peer = self.context.socket(kind)
        peer.linger = 0
        self.sockets.append(peer)
        return peer

    async def test_sub_receives_desktop_pub_two_frame_stream(self):
        port = _free_port()
        reader = ZmqStreamReader(
            "tcp://127.0.0.1:%d" % port, topic="sensor/",
            serializer=self.codec, queue_size=4,
        )
        try:
            await reader.start()
            await asyncio.sleep(0.1)  # First connect fails; reader must retry.
            publisher = self._host_socket(zmq.PUB)
            publisher.bind("tcp://127.0.0.1:%d" % port)
            pending = asyncio.create_task(reader.read(timeout=2))
            # Initial PUB/SUB messages may be lost while subscription settles.
            for _ in range(20):
                await publisher.send_multipart([
                    b"sensor/temp", self.codec.serialize({"value": 42}),
                ])
                await asyncio.sleep(0.05)
                if pending.done():
                    break
            value, topic = await asyncio.wait_for(pending, 2)
            self.assertEqual((value, topic), ({"value": 42}, "sensor/temp"))
        finally:
            await asyncio.wait_for(reader.close(), 2)

    async def test_latest_reader_returns_newest_buffered_message(self):
        publisher = self._host_socket(zmq.PUB)
        port = publisher.bind_to_random_port("tcp://127.0.0.1")
        reader = ZmqStreamReader(
            "tcp://127.0.0.1:%d" % port, topic="sensor/",
            serializer=self.codec, queue_size=4, delivery="latest",
        )
        try:
            await reader.start()
            await reader.wait_connected(timeout=2)
            await asyncio.sleep(0.05)
            for count in range(10):
                await publisher.send_multipart([
                    b"sensor/temp", self.codec.serialize({"count": count}),
                ])
            await asyncio.sleep(0.1)  # Let the background TCP reader fill its buffer.
            value, topic = await reader.read(timeout=1)
            self.assertEqual((value, topic), ({"count": 9}, "sensor/temp"))
        finally:
            await asyncio.wait_for(reader.close(), 2)

    async def test_pub_sends_to_desktop_sub_with_reverse_bind(self):
        subscriber = self._host_socket(zmq.SUB)
        subscriber.setsockopt(zmq.SUBSCRIBE, b"sensor/")
        port = subscriber.bind_to_random_port("tcp://127.0.0.1")
        writer = ZmqStreamWriter(
            "tcp://127.0.0.1:%d" % port, serializer=self.codec,
            queue_size=0, bind=False,
        )
        try:
            await writer.start()
            # PUB/SUB intentionally drops messages before subscription setup.
            # Retry sends until the on-wire subscription has reached the writer.
            for attempt in range(20):
                await writer.write(DictFrame({"value": attempt}, gid="S" * 26,
                                             id=attempt, timestamp="123"),
                                   "sensor/temp")
                if await subscriber.poll(100, zmq.POLLIN):
                    frames = await subscriber.recv_multipart()
                    break
            else:
                self.fail("desktop SUB never received an ESP32-style PUB message")
            self.assertEqual(len(frames), 2)
            self.assertEqual(frames[0], b"sensor/temp")
            decoded = self.codec.deserialize(frames[1])
            self.assertEqual(decoded["name"], "DictFrame")
            self.assertEqual(decoded["value"]["value"], decoded["id"])
        finally:
            await asyncio.wait_for(writer.close(), 2)

    async def test_pub_long_zmtp_frame_reaches_desktop_sub(self):
        subscriber = self._host_socket(zmq.SUB)
        subscriber.setsockopt(zmq.SUBSCRIBE, b"sensor/")
        port = subscriber.bind_to_random_port("tcp://127.0.0.1")
        writer = ZmqStreamWriter(
            "tcp://127.0.0.1:%d" % port, serializer=self.codec, bind=False,
        )
        value = {"sample": "x" * 512}
        self.assertGreater(len(self.codec.serialize(value)), 255)
        try:
            await writer.start()
            for _ in range(20):
                await writer.write(value, "sensor/large")
                if await subscriber.poll(100, zmq.POLLIN):
                    frames = await subscriber.recv_multipart()
                    break
            else:
                self.fail("desktop SUB never received the long ZMTP frame")
            self.assertEqual(frames[0], b"sensor/large")
            self.assertEqual(self.codec.deserialize(frames[1]), value)
        finally:
            await asyncio.wait_for(writer.close(), 2)

    async def test_bound_pub_fans_out_to_two_desktop_subscribers(self):
        port = _free_port()
        writer = ZmqStreamWriter(
            "tcp://127.0.0.1:%d" % port, serializer=self.codec,
            queue_size=0, bind=True,
        )
        subscribers = []
        try:
            await writer.start()
            for _ in range(2):
                peer = self._host_socket(zmq.SUB)
                peer.setsockopt(zmq.SUBSCRIBE, b"sensor/")
                peer.connect("tcp://127.0.0.1:%d" % port)
                subscribers.append(peer)
            # Repeated writes account for normal PUB/SUB slow joiner behavior.
            got = [False, False]
            for attempt in range(20):
                await writer.write({"count": attempt}, "sensor/temp")
                for index, peer in enumerate(subscribers):
                    if got[index]:
                        continue
                    if not await peer.poll(50, zmq.POLLIN):
                        continue
                    frames = await peer.recv_multipart()
                    self.assertEqual(frames[0], b"sensor/temp")
                    self.assertIn("count", self.codec.deserialize(frames[1]))
                    got[index] = True
                if all(got):
                    break
            self.assertEqual(got, [True, True])
        finally:
            await asyncio.wait_for(writer.close(), 2)

    async def test_dealer_calls_desktop_router_with_ack_and_reply(self):
        router = self._host_socket(zmq.ROUTER)
        port = router.bind_to_random_port("tcp://127.0.0.1")
        requester = ZmqRpcRequester(
            "tcp://127.0.0.1:%d" % port, serializer=self.codec,
            identity=b"upy-test", ack_timeout=1, reply_timeout=2,
        )
        try:
            await requester.start()
            task = asyncio.create_task(requester.call({"action": "ping"}, timeout=2))
            frames = await asyncio.wait_for(router.recv_multipart(), 2)
            self.assertEqual(len(frames), 2)
            self.assertEqual(frames[0], b"upy-test")
            request = self.codec.deserialize(frames[1])
            self.assertEqual(request["payload"], {"action": "ping"})
            rid = request["rid"]
            await router.send_multipart([frames[0], self.codec.serialize({"rid": rid, "ack": True})])
            await router.send_multipart([frames[0], self.codec.serialize({
                "rid": rid, "payload": {"ok": True},
            })])
            self.assertEqual(await task, {"ok": True})
        finally:
            await asyncio.wait_for(requester.close(), 2)

    async def test_dealer_demuxes_two_out_of_order_rpc_replies(self):
        router = self._host_socket(zmq.ROUTER)
        port = router.bind_to_random_port("tcp://127.0.0.1")
        requester = ZmqRpcRequester(
            "tcp://127.0.0.1:%d" % port, serializer=self.codec,
            ack_timeout=1, reply_timeout=2, max_pending=2,
        )
        calls = []
        try:
            await requester.start()
            calls = [
                asyncio.create_task(requester.call({"value": value}, timeout=2))
                for value in (1, 2)
            ]
            requests = {}
            for _ in calls:
                frames = await asyncio.wait_for(router.recv_multipart(), 2)
                self.assertEqual(len(frames), 2)
                envelope = self.codec.deserialize(frames[1])
                value = envelope["payload"]["value"]
                requests[value] = (frames[0], envelope["rid"])
            self.assertEqual(set(requests), {1, 2})

            for identity, rid in requests.values():
                await router.send_multipart([
                    identity, self.codec.serialize({"rid": rid, "ack": True}),
                ])
            for value in (2, 1):  # Reverse completion order to test rid routing.
                identity, rid = requests[value]
                await router.send_multipart([
                    identity, self.codec.serialize({"rid": rid, "payload": value * 10}),
                ])
            self.assertEqual(await asyncio.wait_for(asyncio.gather(*calls), 2), [10, 20])
        finally:
            for call in calls:
                if not call.done():
                    call.cancel()
            await asyncio.wait_for(requester.close(), 2)

    async def test_router_serves_desktop_dealer_with_ack_and_reply(self):
        port = _free_port()
        responder = ZmqRpcResponder(
            "tcp://127.0.0.1:%d" % port, serializer=self.codec,
            bind=True, queue_size=4,
        )
        dealer = self._host_socket(zmq.DEALER)
        dealer.setsockopt(zmq.IDENTITY, b"desktop-test")
        try:
            await responder.start()
            dealer.connect("tcp://127.0.0.1:%d" % port)
            task = asyncio.create_task(responder.respond(
                lambda request: {"echo": request["value"]}, timeout=2,
            ))
            await dealer.send(self.codec.serialize({
                "rid": "request-1", "payload": {"value": 23},
            }))
            ack = self.codec.deserialize(await asyncio.wait_for(dealer.recv(), 2))
            reply = self.codec.deserialize(await asyncio.wait_for(dealer.recv(), 2))
            self.assertEqual(ack, {"rid": "request-1", "ack": True})
            self.assertEqual(reply, {"rid": "request-1", "payload": {"echo": 23}})
            self.assertTrue(await task)
        finally:
            await asyncio.wait_for(responder.close(), 2)

    async def test_router_routes_two_desktop_callers_separately(self):
        port = _free_port()
        responder = ZmqRpcResponder(
            "tcp://127.0.0.1:%d" % port, serializer=self.codec,
            bind=True, queue_size=4,
        )
        callers = []
        try:
            await responder.start()
            for name in (b"desktop-a", b"desktop-b"):
                caller = self._host_socket(zmq.DEALER)
                caller.setsockopt(zmq.IDENTITY, name)
                caller.connect("tcp://127.0.0.1:%d" % port)
                callers.append(caller)

            await asyncio.gather(*[
                caller.send(self.codec.serialize({
                    "rid": "rid-%d" % index,
                    "payload": {"client": index},
                }))
                for index, caller in enumerate(callers)
            ])
            for _ in callers:
                self.assertTrue(await responder.respond(
                    lambda request: {"client": request["client"]}, timeout=2,
                ))
            for index, caller in enumerate(callers):
                ack = self.codec.deserialize(await asyncio.wait_for(caller.recv(), 2))
                reply = self.codec.deserialize(await asyncio.wait_for(caller.recv(), 2))
                self.assertEqual(ack, {"rid": "rid-%d" % index, "ack": True})
                self.assertEqual(reply, {
                    "rid": "rid-%d" % index,
                    "payload": {"client": index},
                })
        finally:
            await asyncio.wait_for(responder.close(), 2)

    async def test_mcp_tool_call_over_desktop_dealer(self):
        schema = McpSchema(name="esp32-test")
        schema.register(
            "read_pin", lambda pin: {"pin": pin, "value": 1},
            input_schema={"type": "object", "properties": {"pin": {"type": "integer"}}},
            output_schema={"type": "object"},
        )
        port = _free_port()
        responder = ZmqRpcResponder(
            "tcp://127.0.0.1:%d" % port, serializer=self.codec,
            schema=schema, bind=True,
        )
        dealer = self._host_socket(zmq.DEALER)
        try:
            await responder.start()
            dealer.connect("tcp://127.0.0.1:%d" % port)
            task = asyncio.create_task(responder.respond(timeout=2))
            await dealer.send(self.codec.serialize({
                "rid": "mcp-1",
                "payload": {
                    "jsonrpc": "2.0", "method": "tools/call", "id": 1,
                    "params": {"name": "read_pin", "arguments": {"pin": 21}},
                },
            }))
            ack = self.codec.deserialize(await asyncio.wait_for(dealer.recv(), 2))
            reply = self.codec.deserialize(await asyncio.wait_for(dealer.recv(), 2))
            self.assertEqual(ack, {"rid": "mcp-1", "ack": True})
            self.assertEqual(reply["rid"], "mcp-1")
            self.assertEqual(reply["payload"]["result"]["structuredContent"], {
                "pin": 21, "value": 1,
            })
            self.assertTrue(await task)
        finally:
            await asyncio.wait_for(responder.close(), 2)


if __name__ == "__main__":
    unittest.main()
