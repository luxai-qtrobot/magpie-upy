# Board examples

The MQTT scripts contain their own `DEVICE_ID` and `MQTT_CONFIG` near the top.
Replace `YOUR_WIFI` and `YOUR_WIFI_PASSWORD` in the script you want to run.
Give each board a distinct device ID and MQTT client ID, and keep real
credentials out of commits. From the repository root, install the optional
MQTT manifest for these scripts:

```powershell
mpremote connect COM13 mip install package-mqtt.json
```

The MQTT desktop commands need MAGPIE's MQTT extra installed.

Open two PowerShell windows. Run one board script in the first window and leave
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

## ZMQ on a local network

The ZMQ examples use direct TCP and no broker. From this checkout, install the
default manifest on the board and desktop MAGPIE on your computer:

```powershell
mpremote connect COM13 mip install package.json
python -m pip install luxai-magpie
```

Edit `WIFI_SSID` and `WIFI_PASSWORD` in the chosen board script. These examples
establish the initial Wi-Fi connection; the ZMQ transport reconnects its own
TCP sockets but does not manage Wi-Fi. Use the board's network manager if your
application must restore Wi-Fi after an outage.

### Board publisher to desktop reader

Run [`zmq_sensor_stream.py`](zmq_sensor_stream.py) on the board first. It binds
TCP port 5555 and prints its IP address:

```powershell
mpremote connect COM13 run examples/zmq_sensor_stream.py
```

In a second terminal, connect the desktop reader to that address:

```powershell
magpie-read.exe tcp://BOARD_IP:5555 magpie-upy/esp32-001/sensor --pretty
```

The script publishes a `DictFrame` with a stable GID, increasing frame ID,
counter, and free heap every two seconds. This frame also works with C++
MAGPIE readers. Initial PUB/SUB messages can be lost while the subscription
is established.

### Desktop publisher to board reader

Run [`zmq_stream_reader.py`](zmq_stream_reader.py) on the board first. It binds
TCP port 5557 and prints its IP address:

```powershell
mpremote connect COM13 run examples/zmq_stream_reader.py
```

In a second terminal, publish to the board:

```powershell
magpie-write.exe tcp://BOARD_IP:5557 magpie-upy/esp32-001/command "{'action':'ping'}" --rate 1 --loop
```

The reader prints the incoming MAGPIE `DictFrame` dictionaries. It uses
`delivery="latest"` so a slow application prefers the newest buffered value.

### Board user LED over ZMQ RPC

Run [`zmq_rpc_switch.py`](zmq_rpc_switch.py) on a XIAO ESP32-S3 and note the
board IP it prints:

```powershell
mpremote connect COM13 run examples/zmq_rpc_switch.py
```

In a second terminal, send the same `on` and `off` requests as the MQTT switch
example, using the board's ZMQ endpoint:

```powershell
magpie-request.exe tcp://BOARD_IP:5558 "{'action':'on'}" --pretty
magpie-request.exe tcp://BOARD_IP:5558 "{'action':'off'}" --pretty
```

GPIO21 is active low: the `on` request lights the user LED, and `off` turns it
off. The example also turns the LED off when stopped.

### Board MCP tool over ZMQ RPC

Run [`zmq_mcp_tool.py`](zmq_mcp_tool.py) on the board:

```powershell
mpremote connect COM13 run examples/zmq_mcp_tool.py
```

It prints the board's IP address and listens on port 5556. Replace `BOARD_IP`
below with that address, then discover and call the `free_memory` tool:

```powershell
magpie-request.exe tcp://BOARD_IP:5556 "{'jsonrpc':'2.0','id':1,'method':'tools/list'}" --pretty
magpie-request.exe tcp://BOARD_IP:5556 "{'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'free_memory','arguments':{}}}" --pretty
```

The board runs a ROUTER socket and the desktop requester connects as a
DEALER. On Linux or macOS, omit `.exe` from the commands. The source examples
use plain ZMTP/TCP with NULL security; keep their ports on a trusted network.

