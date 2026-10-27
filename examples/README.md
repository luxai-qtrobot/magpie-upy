# ESP32 examples

Each script contains its own `DEVICE_ID` and `MQTT_CONFIG` near the top.
Replace `YOUR_WIFI` and `YOUR_WIFI_PASSWORD` in the script you want to run.
Give each board a distinct device ID and MQTT client ID, and keep real
credentials out of commits. Install this package on the board as described in
the project README. The desktop commands need MAGPIE's MQTT extra installed.

Open two PowerShell windows. Run one ESP32 script in the first window and leave
it running; run its matching MAGPIE command in the second. Replace `COM13` with
your serial port. Stop the script before starting another one on the same board.

## Sensor stream

Publish the counter and free heap every two seconds:

```powershell
mpremote connect COM13 run examples/mqtt_sensor_stream.py
```

Read the stream with desktop MAGPIE:

```powershell
magpie-read-mqtt.exe mqtt://broker.hivemq.com:1883 magpie-upy/esp32-001/sensor --pretty
```

You should see `count` increase in each received dictionary.

## User LED RPC

Start the XIAO ESP32-S3 user LED service:

```powershell
mpremote connect COM13 run examples/mqtt_rpc_switch.py
```

Call it from desktop MAGPIE:

```powershell
magpie-request-mqtt.exe mqtt://broker.hivemq.com:1883 esp32-001/switch "{'action': 'on'}" --pretty
magpie-request-mqtt.exe mqtt://broker.hivemq.com:1883 esp32-001/switch "{'action': 'off'}" --pretty
```

The first call turns the user LED on; the second turns it off. Each reply
reports the requested `action`. Seeed documents the
[GPIO21 user LED](https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/)
as [active low](https://wiki.seeedstudio.com/xiao-esp32s3-freertos/), so
`led.off()` lights it and `led.on()` extinguishes it.

## MCP tool

Start the `free_memory` tool service:

```powershell
mpremote connect COM13 run examples/mqtt_mcp_tool.py
```

Discover its tools and then call `free_memory` from desktop MAGPIE:

```powershell
magpie-request-mqtt.exe mqtt://broker.hivemq.com:1883 esp32-001/mcp "{'jsonrpc':'2.0','id':1,'method':'tools/list'}" --pretty
magpie-request-mqtt.exe mqtt://broker.hivemq.com:1883 esp32-001/mcp "{'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'free_memory','arguments':{}}}" --pretty
```

The first reply lists `free_memory`; the second contains the board's free heap
in bytes. To discover and call the same tool through a desktop FastMCP client,
install the desktop extras, save the Python code as `mcp_client.py`, and run it
while the board example is running:

```powershell
python -m pip install "luxai-magpie[mqtt,mcp]"
```

```python
import asyncio

from fastmcp import Client
from luxai.magpie.adapters.mcp import McpTransport
from luxai.magpie.transport.mqtt import MqttConnection, MqttRpcRequester


async def main():
    conn = MqttConnection("mqtt://broker.hivemq.com:1883", protocol_version=3)
    conn.connect()
    requester = MqttRpcRequester(conn, service_name="esp32-001/mcp")
    try:
        async with Client(McpTransport(requester, timeout=15)) as client:
            for tool in await client.list_tools():
                print(tool.name, tool.description)
            result = await client.call_tool("free_memory", {})
            print(result.content[0].text)
    finally:
        requester.close()
        conn.disconnect()


asyncio.run(main())
```

```powershell
python mcp_client.py
```

If you change the broker or `DEVICE_ID` in an example, update its desktop
command too. The board's `MQTT_CONFIG["server"]` takes a hostname; the desktop
CLI takes an `mqtt://` URL. On Linux or macOS, omit `.exe` from the CLI names.

