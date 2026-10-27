"""Desktop MAGPIE responder for device_requester_smoke.py."""

from luxai.magpie.transport.mqtt import MqttConnection, MqttRpcResponder


SERVICE = "luxai/magpie-upy/smoke-com13-20261027/desktop"


def handle(request):
    assert request == {"from": "esp32", "n": 11}, request
    return {"from": "desktop", "n": request["n"] + 1}


def main():
    connection = MqttConnection("mqtt://broker.hivemq.com:1883", protocol_version=3)
    connection.connect(timeout=10)
    responder = MqttRpcResponder(connection, SERVICE)
    try:
        print("host_responder_ready", flush=True)
        responder.respond(handler=handle, timeout=30)
        print("host_responder_smoke_ok")
    finally:
        responder.close()
        connection.disconnect()


if __name__ == "__main__":
    main()
