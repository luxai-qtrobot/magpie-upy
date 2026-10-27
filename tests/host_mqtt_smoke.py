"""Desktop MAGPIE side of the COM13 MQTT interoperability check.

Run with the desktop MAGPIE Python environment, after device_mqtt_smoke.py
prints device_ready. Both sides use the public HiveMQ broker.
"""

from luxai.magpie.frames import Frame
from luxai.magpie.schema import McpSchema
from luxai.magpie.transport.mqtt import (
    MqttConnection, MqttStreamReader, MqttStreamWriter, MqttRpcRequester,
)


PREFIX = "luxai/magpie-upy/smoke-com13-20261027"


def main():
    connection = MqttConnection(
        "mqtt://broker.hivemq.com:1883", protocol_version=3,
    )
    connection.connect(timeout=10)
    reader = MqttStreamReader(connection, PREFIX + "/output", queue_size=0)
    writer = MqttStreamWriter(connection, queue_size=0)
    raw_rpc = MqttRpcRequester(connection, PREFIX + "/raw")
    mcp_rpc = MqttRpcRequester(
        connection, PREFIX + "/mcp", schema=McpSchema(),
    )
    try:
        writer.write({"from": "desktop", "n": 7}, PREFIX + "/input")
        received, _topic = reader.read(timeout=15)
        frame = Frame.from_dict(received)
        assert frame.name == "IntFrame" and frame.value == 42 and frame.id == 3

        response = raw_rpc.call({"action": "ping"}, timeout=15)
        assert response == {"from": "esp32", "echo": {"action": "ping"}}
        initialize = mcp_rpc.call("initialize", timeout=15)
        assert initialize["serverInfo"]["name"] == "esp32-smoke"
        tools = mcp_rpc.call("tools/list", timeout=15)
        assert tools["tools"][0]["name"] == "read_value"
        result = mcp_rpc.call(
            "tools/call", timeout=15, name="read_value", arguments={},
        )
        assert result["structuredContent"] == {"value": 42}
        print("host_mqtt_smoke_ok")
    finally:
        reader.close()
        writer.close()
        raw_rpc.close()
        mcp_rpc.close()
        connection.disconnect()


if __name__ == "__main__":
    main()
