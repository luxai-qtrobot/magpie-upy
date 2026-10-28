<p align="center">
  <img src="https://github.com/luxai-qtrobot/magpie/raw/main/src/luxai/magpie/assets/magpie.png" alt="MAGPIE logo" width="200"/>
</p>

<h1 align="center">MAGPIE for MicroPython</h1>
<p align="center"><em>Message Abstraction & General-Purpose Integration Engine</em></p>

<p align="center">
  <a href="#installation"><img src="https://img.shields.io/badge/platform-MicroPython-2f855a" alt="Platform: MicroPython"/></a>
  <a href="#installation"><img src="https://img.shields.io/badge/boards-ESP32%20%26%20Pico%20W-e69534" alt="Boards: ESP32 and Pico W"/></a>
  <a href="#features"><img src="https://img.shields.io/badge/transport-ZMQ%20%2B%20MQTT-8b5cf6" alt="Transports: ZMQ and MQTT"/></a>
  <a href="#mcp-tool"><img src="https://img.shields.io/badge/MCP-tools-118e78" alt="MCP tools"/></a>
  <a href="#installation"><img src="https://img.shields.io/badge/install-mip-3b82f6" alt="Install with mip"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPLv3-6b7280" alt="License: GPLv3"/></a>
</p>

MAGPIE for MicroPython brings asynchronous streams, request/reply RPC, typed frames, and MCP tools to embedded boards. Its default ZMQ and optional MQTT transports exchange the same MAGPIE MessagePack values and RPC envelopes as [MAGPIE for Python](https://github.com/luxai-qtrobot/magpie), so a MicroPython device can communicate with desktop applications and tools.

Repository: [luxai-qtrobot/magpie-upy](https://github.com/luxai-qtrobot/magpie-upy).

The stream, RPC, and serializer layers are transport independent. The implementation uses MicroPython's `asyncio` rather than desktop MAGPIE's threads.

---

## Contents

- [Features](#features)
- [Installation](#installation)
- [Quick start](#quick-start)
  - [Sensor stream](#sensor-stream)
  - [User LED RPC](#user-led-rpc)
  - [MCP tool](#mcp-tool)
  - [Direct ZMQ on a LAN](#direct-zmq-on-a-lan)
- [Core API](#core-api)
- [Architecture and scope](#architecture-and-scope)
- [Examples and tests](#examples-and-tests)
- [Related projects](#related-projects)
- [License](#license)

---

## Features

| Capability | On the MicroPython board |
|---|---|
| Streams | `await writer.write(value, topic)` and `await reader.read(timeout)` over MQTT or ZMQ |
| RPC | `await requester.call(request)` and `await responder.respond(handler)`, with an ACK and a separate reply |
| Schemas | `JsonRpcSchema` for JSON-RPC methods; `McpSchema` for MCP tool discovery and calls |
| Frames | Optional `BoolFrame`, `IntFrame`, `FloatFrame`, `StringFrame`, `BytesFrame`, `DictFrame`, and `ListFrame` |
| Serialization | MessagePack by default, behind a replaceable serializer interface |
| ZMQ | Direct TCP PUB/SUB streams and DEALER/ROUTER RPC, interoperable with desktop MAGPIE |
| MQTT | One `MqttConnection` can be shared by stream and RPC components; `mqtt_as` handles networking and reconnection |
| Logging | Small colored `Logger` with debug, info, warning, and error levels |

A stream may carry a plain value or a frame. The board can publish to a desktop MAGPIE reader, receive a desktop stream, call a desktop RPC service, or serve requests from a desktop client.

---

## Installation

### Requirements

- A MicroPython board with `asyncio`, TCP networking, and enough memory for the chosen transport. The examples use Wi-Fi.
- For MQTT, a reachable broker and a board supported by `mqtt_as`. The examples use the public `broker.hivemq.com` broker. ZMQ needs a reachable TCP peer instead of a broker.
- `mpremote` on your computer to install the package and run the examples over USB.

The package itself does not depend on a specific board. Its MQTT dependency, [`mqtt_as`](https://github.com/peterhinch/micropython-mqtt), documents support for ESP32, ESP8266, Raspberry Pi Pico W, and other MicroPython targets. MAGPIE device testing so far used a Seeed XIAO ESP32-S3 running MicroPython 1.29.0; check firmware, available memory, and networking on other boards. ESP8266 may need `mqtt_as` precompiled or frozen because of its memory limits.

The default [`package.json`](package.json) installs the shared core, ZMQ adapter, and [`umsgpack`](https://github.com/peterhinch/micropython-msgpack), without `mqtt_as`. The optional [`package-mqtt.json`](package-mqtt.json) installs the shared core, MQTT adapter, `umsgpack`, and [`mqtt_as`](https://github.com/peterhinch/micropython-mqtt). Install both manifests to use both transports. `pip` installs desktop tools on your computer; `mip` installs MicroPython files on the board.

### Install from this checkout

Run these commands from the repository root. Replace `COM13` with your serial port, such as `/dev/ttyACM0` on Linux.

```powershell
python -m pip install mpremote
mpremote connect COM13 mip install package.json
```

For MQTT, install its manifest instead. Install both manifests if you need both transports:

```powershell
mpremote connect COM13 mip install package-mqtt.json
```

`mpremote` uses the computer to fetch and copy the package. The board needs network connectivity when it runs either transport.

### Install from GitHub

```powershell
mpremote connect COM13 mip install github:luxai-qtrobot/magpie-upy
```

For MQTT, use its manifest:

```powershell
mpremote connect COM13 mip install github:luxai-qtrobot/magpie-upy/package-mqtt.json
```

On a network-connected board, the equivalent REPL command is:

```python
import mip
mip.install("github:luxai-qtrobot/magpie-upy")
```

For MQTT on the board, use `mip.install("github:luxai-qtrobot/magpie-upy/package-mqtt.json")`.

MicroPython's [`mip` package index](https://docs.micropython.org/en/latest/reference/packages.html) is separate from PyPI. MAGPIE for MicroPython is not currently listed in that index, so installation by a bare package name is not yet available. The [`luxai-magpie` PyPI package](https://pypi.org/project/luxai-magpie/) is for desktop Python.

### Install the desktop companion

For the ZMQ command-line tools, install desktop MAGPIE:

```powershell
python -m pip install luxai-magpie
```

For the MQTT command-line tools used below, install its MQTT extra:

```powershell
python -m pip install "luxai-magpie[mqtt]"
```

For the FastMCP client example, install the MCP extra too:

```powershell
python -m pip install "luxai-magpie[mqtt,mcp]"
```

---

## Quick start

The MQTT examples below require `package-mqtt.json`. Each MQTT script in [`examples/`](examples/README.md) has its own `DEVICE_ID` and `MQTT_CONFIG`. Replace the Wi-Fi placeholders before running a script. Give each board a unique device ID and MQTT client ID. The `server` setting is a hostname such as `broker.hivemq.com`, while desktop MAGPIE accepts an `mqtt://` URL.

### Sensor stream

The sensor example publishes a counter and free heap every two seconds:

```powershell
mpremote connect COM13 run examples/mqtt_sensor_stream.py
```

In another terminal, read it with desktop MAGPIE:

```powershell
magpie-read-mqtt mqtt://broker.hivemq.com:1883 magpie-upy/esp32-001/sensor --pretty
```

A minimal publisher follows the same pattern:

```python
import asyncio
from luxai.magpie.transport.mqtt import MqttConnection, MqttStreamWriter

MQTT_CONFIG = {
    "ssid": "YOUR_WIFI",
    "wifi_pw": "YOUR_WIFI_PASSWORD",
    "server": "broker.hivemq.com",
    "port": 1883,
    "client_id": b"magpie-upy-esp32-001",
}

async def main():
    conn = MqttConnection(MQTT_CONFIG)
    writer = MqttStreamWriter(conn)
    try:
        await conn.connect()
        count = 0
        while True:
            await writer.write({"count": count}, "magpie-upy/esp32-001/sensor")
            count += 1
            await asyncio.sleep(2)
    finally:
        await writer.close()
        conn.close()

asyncio.run(main())
```

### User LED RPC

On a XIAO ESP32-S3, the RPC example controls the active-low user LED on GPIO21:

```powershell
mpremote connect COM13 run examples/mqtt_rpc_switch.py
```

Call it from desktop MAGPIE in another terminal:

```powershell
magpie-request-mqtt mqtt://broker.hivemq.com:1883 esp32-001/switch "{'action':'on'}" --pretty
magpie-request-mqtt mqtt://broker.hivemq.com:1883 esp32-001/switch "{'action':'off'}" --pretty
```

The board's [`mqtt_rpc_switch.py`](examples/mqtt_rpc_switch.py) creates one `MqttRpcResponder`, starts it, and repeatedly awaits `respond(handler=..., timeout=1)`. Each call receives an ACK and then a reply. `respond()` handles one request and returns `False` on timeout.

### MCP tool

The board can expose tools without running FastMCP or an HTTP server. [`mqtt_mcp_tool.py`](examples/mqtt_mcp_tool.py) registers `free_memory` with `McpSchema` and serves it through MAGPIE MQTT RPC:

```powershell
mpremote connect COM13 run examples/mqtt_mcp_tool.py
```

Discover and call the tool with the desktop request CLI:

```powershell
magpie-request-mqtt mqtt://broker.hivemq.com:1883 esp32-001/mcp "{'jsonrpc':'2.0','id':1,'method':'tools/list'}" --pretty
magpie-request-mqtt mqtt://broker.hivemq.com:1883 esp32-001/mcp "{'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'free_memory','arguments':{}}}" --pretty
```

A desktop FastMCP client can use MAGPIE's `McpTransport` to discover and call the same tool:

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

See [the example guide](examples/README.md#mcp-tool) for the full run instructions. `McpSchema` supports MCP tool discovery and calls; the desktop adapter handles the FastMCP client connection.

### Direct ZMQ on a LAN

ZMQ runs directly over TCP without a broker. The application connects Wi-Fi first; the ZMQ classes manage their own TCP/ZMTP connections and reconnects, not the board's Wi-Fi interface. For a board publisher, set the Wi-Fi credentials in [`zmq_sensor_stream.py`](examples/zmq_sensor_stream.py), run it, and note the board IP it prints:

```powershell
mpremote connect COM13 run examples/zmq_sensor_stream.py
magpie-read tcp://BOARD_IP:5555 magpie-upy/esp32-001/sensor --pretty
```

For a simple RPC service, [`zmq_rpc_switch.py`](examples/zmq_rpc_switch.py) controls the XIAO user LED with the same `on` and `off` requests as the MQTT switch example. The board can also serve MCP tools directly. Run [`zmq_mcp_tool.py`](examples/zmq_mcp_tool.py), note the board IP it prints, then call it with `magpie-request`:

```powershell
mpremote connect COM13 run examples/zmq_mcp_tool.py
magpie-request tcp://BOARD_IP:5556 "{'jsonrpc':'2.0','id':1,'method':'tools/list'}" --pretty
```

Run the board script and desktop command in separate terminals. The [example guide](examples/README.md#zmq-on-a-local-network) has the full commands, including a tool call.

---

## Core API

The four application operations match desktop MAGPIE's concepts. On MicroPython, all four are asynchronous:

| Operation | MicroPython API | Result |
|---|---|---|
| Publish | `await writer.write(value, topic)` | Sends a value on a stream topic |
| Subscribe | `value, topic = await reader.read(timeout=5)` | Reads the next value and its topic |
| Request | `reply = await requester.call(request, timeout=5)` | Waits for the RPC reply |
| Respond | `await responder.respond(handler=handler, timeout=1)` | Handles one request, or returns `False` on timeout |

For MQTT, create one `MqttConnection` and pass it to stream writers, readers, requesters, and responders. After `await conn.connect()`, call `await reader.start()` or `await responder.start()` before traffic begins so their subscriptions are ready. Close each component with `await component.close()`, then call `conn.close()`. ZMQ classes each take a `tcp://` endpoint; call `await start()` before traffic and `await close()` when finished.

### Optional frames

Frames add MAGPIE metadata (`gid`, `id`, `name`, and `timestamp`) to a stream value. A series of related frames can keep one `gid` and increment `id`:

```python
from luxai.magpie.frames import Frame, IntFrame

first = IntFrame(0)
second = IntFrame(1, gid=first.gid, id=1)
restored = Frame.from_dict(second.to_dict())
print(restored.value)  # 1
```

In an async stream, send one with `await writer.write(second, "sensors/count")`. A reader receives a dictionary; use `Frame.from_dict(value)` to reconstruct the typed frame.

Plain values need no wrapper. The default `MsgpackSerializer` converts values and frames to MessagePack; applications can supply another serializer through the core interfaces. A board without a set clock uses frame timestamp `"0"` rather than a false wall-clock time.

---

## Architecture and scope

```text
MicroPython application
  -> async StreamWriter / StreamReader / RpcRequester / RpcResponder
  -> serializer (MessagePack by default)
  -> ZMQ adapter -> direct TCP peer, or optional MQTT adapter -> broker
  -> desktop MAGPIE, another board, or another compatible peer
```

The core stream/RPC classes and serializer interface do not depend on a specific transport. The MQTT writer uses no worker thread or writer queue; its readers and responders have bounded incoming mailboxes. The ZMQ adapter uses bounded async buffers where needed for multiple TCP peers. RPC handlers run one at a time per responder, so long-running handlers should yield or be split into shorter work.

The default MQTT payload limit is 4096 bytes. Default stream and RPC publishes use QoS 1. The ZMQ adapter supports TCP with ZMTP 3.0/3.1 NULL security, PUB/SUB streams, and DEALER/ROUTER RPC; it does not provide the full libzmq API or encrypted ZeroMQ mechanisms. ZMQ messages default to an 8192-byte limit, bound sockets accept up to four peers, and a publisher accepts up to 16 subscriptions or 512 prefix bytes per peer; these limits are configurable. Keep NULL-security endpoints on a trusted local network or protected tunnel.

ZMQ stream writers and readers accept `bind`, `queue_size`, and `delivery="reliable"` or `"latest"`. `queue_size` is a bounded application buffer; a writer size of zero adds no application queue. `reliable` retains ordinary ZeroMQ PUB/SUB best-effort behavior, not guaranteed delivery. `latest` favors fresh data: the writer uses a small per-peer send buffer and the reader discards older buffered values on `read()`. This is a MicroPython approximation of desktop MAGPIE's high-water-mark setting, not identical libzmq buffering. WebRTC, audio/video frames, desktop-style CLI tools, and an HTTP MCP server are not included in this device package.

For an application with real devices, use your own broker and configure its authentication in `MQTT_CONFIG`. The public broker in these examples is for demonstrations.

---

## Examples and tests

| Example | Device behavior | Desktop companion |
|---|---|---|
| [Sensor stream](examples/mqtt_sensor_stream.py) | Publishes counter and free heap | `magpie-read-mqtt` |
| [User LED RPC](examples/mqtt_rpc_switch.py) | Responds to `on` and `off` requests | `magpie-request-mqtt` |
| [MCP tool](examples/mqtt_mcp_tool.py) | Exposes `free_memory` | `magpie-request-mqtt` or FastMCP `Client` |
| [ZMQ sensor stream](examples/zmq_sensor_stream.py) | Publishes over direct TCP | `magpie-read` |
| [ZMQ stream reader](examples/zmq_stream_reader.py) | Receives a desktop stream over direct TCP | `magpie-write` |
| [ZMQ user LED RPC](examples/zmq_rpc_switch.py) | Responds to `on` and `off` over direct TCP | `magpie-request` |
| [ZMQ MCP tool](examples/zmq_mcp_tool.py) | Serves a tool over direct TCP | `magpie-request` |

The [example guide](examples/README.md) pairs every device script with working desktop commands. The [test guide](tests/README.md) covers host checks and ESP32 interoperability checks.

To run the host tests from this checkout, install `msgpack` and `pyzmq` on your computer and run:

```powershell
python -m pip install msgpack pyzmq
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m unittest discover -s tests -p "test_*.py"
```

On Linux or macOS, use `PYTHONPATH=src python -m unittest discover -s tests -p 'test_*.py'`.

The host MQTT tests use an in-memory broker; the ZMQ tests exchange real TCP frames with PyZMQ. Hardware tests use the board and broker described in [`tests/README.md`](tests/README.md).

---

## Related projects

| Project | Repository |
|---|---|
| MAGPIE for Python | [luxai-qtrobot/magpie](https://github.com/luxai-qtrobot/magpie) |
| MAGPIE.js | [luxai-qtrobot/magpie-js](https://github.com/luxai-qtrobot/magpie-js) |
| MAGPIE C++ | [luxai-qtrobot/magpie-cpp](https://github.com/luxai-qtrobot/magpie-cpp) |

## License

Licensed under the [GNU General Public License v3 (GPLv3)](LICENSE), matching desktop MAGPIE.
