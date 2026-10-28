"""Inspect ESP32 ZMQ smoke traffic: python tests/host_device_zmq_smoke.py BOARD_IP."""

import sys
import time

import msgpack
import zmq


def main(host):
    context = zmq.Context()
    subscriber = context.socket(zmq.SUB)
    subscriber.setsockopt(zmq.SUBSCRIBE, b"magpie-upy/zmq/sensor")
    subscriber.connect("tcp://%s:58671" % host)
    dealer = context.socket(zmq.DEALER)
    dealer.setsockopt(zmq.IDENTITY, b"host-zmq-smoke")
    dealer.connect("tcp://%s:58672" % host)
    poller = zmq.Poller()
    poller.register(subscriber, zmq.POLLIN)
    poller.register(dealer, zmq.POLLIN)
    try:
        # Give subscriptions and the DEALER connection time to settle.
        time.sleep(0.5)
        dealer.send(msgpack.packb({"rid": "smoke-1", "payload": {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "free_heap", "arguments": {}},
        }}, use_bin_type=True))
        received_stream = False
        received_ack = False
        received_reply = False
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not all((
                received_stream, received_ack, received_reply)):
            events = dict(poller.poll(1000))
            if subscriber in events:
                parts = subscriber.recv_multipart()
                value = msgpack.unpackb(parts[1], raw=False)
                assert value["blob"] == "x" * 512
                print("stream", parts[0], value["count"], len(value["blob"]))
                received_stream = True
            if dealer in events:
                parts = dealer.recv_multipart()
                print("rpc_parts", len(parts), [len(part) for part in parts])
                message = msgpack.unpackb(parts[-1], raw=False)
                print("rpc", message)
                received_ack |= message.get("ack") is True
                received_reply |= "payload" in message
        if not all((received_stream, received_ack, received_reply)):
            raise RuntimeError("missing stream, ACK, or reply")
    finally:
        subscriber.close(0)
        dealer.close(0)
        context.term()


if __name__ == "__main__":
    main(sys.argv[1])
