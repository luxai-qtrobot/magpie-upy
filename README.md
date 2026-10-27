<p align="center">
  <img src="https://github.com/luxai-qtrobot/magpie/raw/main/src/luxai/magpie/assets/magpie.png" alt="MAGPIE logo" width="200"/>
</p>

<h1 align="center">MAGPIE for MicroPython</h1>
<p align="center"><em>Message Abstraction & General-Purpose Integration Engine</em></p>

<p align="center">
  <a href="#installation"><img src="https://img.shields.io/badge/platform-MicroPython-2f855a" alt="Platform: MicroPython"/></a>
  <a href="#installation"><img src="https://img.shields.io/badge/board-ESP32--S3-e69534" alt="Tested board: ESP32-S3"/></a>
  <a href="#features"><img src="https://img.shields.io/badge/transport-MQTT-8b5cf6" alt="Transport: MQTT"/></a>
  <a href="#mcp-tool"><img src="https://img.shields.io/badge/MCP-tools-118e78" alt="MCP tools"/></a>
  <a href="#installation"><img src="https://img.shields.io/badge/install-mip-3b82f6" alt="Install with mip"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPLv3-6b7280" alt="License: GPLv3"/></a>
</p>

MAGPIE for MicroPython brings asynchronous streams, request/reply RPC, typed frames, and MCP tools to embedded boards. It uses the same MQTT topics, MessagePack payloads, and RPC envelopes as [MAGPIE for Python](https://github.com/luxai-qtrobot/magpie), so an ESP32 can exchange data with desktop applications and tools.

Repository: [luxai-qtrobot/magpie-upy](https://github.com/luxai-qtrobot/magpie-upy).

**MQTT is the only transport supplied in this release.** The stream, RPC, and serializer layers remain separate from MQTT, keeping the core API small and allowing other adapters to be added later. The implementation uses MicroPython's `asyncio` rather than desktop MAGPIE's threads.

---

## Contents

- [Features](#features)
- [Installation](#installation)
- [Quick start](#quick-start)
  - [Sensor stream](#sensor-stream)
  - [User LED RPC](#user-led-rpc)
  - [MCP tool](#mcp-tool)
- [Core API](#core-api)
- [Architecture and scope](#architecture-and-scope)
- [Examples and tests](#examples-and-tests)
- [Related projects](#related-projects)
- [License](#license)

---

## Features

| Capability | On the MicroPython board |
|---|---|
| Streams | `await writer.write(value, topic)` and `await reader.read(timeout)` over MQTT topics |
| RPC | `await requester.call(request)` and `await responder.respond(handler)`, with an ACK and a separate reply |
| Schemas | `JsonRpcSchema` for JSON-RPC methods; `McpSchema` for MCP tool discovery and calls |
| Frames | Optional `BoolFrame`, `IntFrame`, `FloatFrame`, `StringFrame`, `BytesFrame`, `DictFrame`, and `ListFrame` |
| Serialization | MessagePack by default, behind a replaceable serializer interface |
| MQTT | One `MqttConnection` can be shared by stream and RPC components; `mqtt_as` handles networking and reconnection |
| Logging | Small colored `Logger` with debug, info, warning, and error levels |

A stream may carry a plain value or a frame. The board can publish to a desktop MAGPIE reader, receive a desktop stream, call a desktop RPC service, or serve requests from a desktop client.

---

## Installation

### Requirements

- A network-capable MicroPython board with `asyncio`. Development and device testing used a Seeed XIAO ESP32-S3 running MicroPython 1.29.0.
- An MQTT broker reachable by the board and its peers. The examples use the public `broker.hivemq.com` broker.
- `mpremote` on your computer to install the package and run the examples over USB.

The [`package.json`](package.json) manifest installs MAGPIE, [`mqtt_as`](https://github.com/peterhinch/micropython-mqtt), and [`umsgpack`](https://github.com/peterhinch/micropython-msgpack). `pip` installs the desktop tools on your computer; `mip` installs MicroPython files on the board.

### Install from this checkout

Run these commands from the repository root. Replace `COM13` with your serial port, such as `/dev/ttyACM0` on Linux.

```powershell
python -m pip install mpremote
mpremote connect COM13 mip install package.json
```

`mpremote` uses the computer to fetch and copy the package. The board needs Wi-Fi when it runs an MQTT example.

### Install a tagged release from GitHub

Once the code and `v0.1.0` tag are pushed to [luxai-qtrobot/magpie-upy](https://github.com/luxai-qtrobot/magpie-upy), users can install the tagged version without cloning it:

```powershell
mpremote connect COM13 mip install github:luxai-qtrobot/magpie-upy@v0.1.0
```

On a network-connected board, the equivalent REPL command is:

```python
import mip
mip.install("github:luxai-qtrobot/magpie-upy", version="v0.1.0")
```

MicroPython's [`mip` package index](https://docs.micropython.org/en/latest/reference/packages.html) is separate from PyPI. MAGPIE for MicroPython is not currently listed in that index, so installation by a bare package name is not yet available. The [`luxai-magpie` PyPI package](https://pypi.org/project/luxai-magpie/) is for desktop Python.

### Install the desktop companion

For the MQTT command-line tools used below:

```powershell
python -m pip install "luxai-magpie[mqtt]"
```

For the FastMCP client example, install the MCP extra too:

```powershell
python -m pip install "luxai-magpie[mqtt,mcp]"
```

---

## Quick start

Each script in [`examples/`](examples/README.md) has its own `DEVICE_ID` and `MQTT_CONFIG`. Replace the Wi-Fi placeholders before running a script. Give each board a unique device ID and MQTT client ID. The `server` setting is a hostname such as `broker.hivemq.com`, while desktop MAGPIE accepts an `mqtt://` URL.

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

---

## Core API

The four application operations match desktop MAGPIE's concepts. On MicroPython, all four are asynchronous:

| Operation | MicroPython API | Result |
|---|---|---|
| Publish | `await writer.write(value, topic)` | Sends a value on an MQTT topic |
| Subscribe | `value, topic = await reader.read(timeout=5)` | Reads the next value and its topic |
| Request | `reply = await requester.call(request, timeout=5)` | Waits for the RPC reply |
| Respond | `await responder.respond(handler=handler, timeout=1)` | Handles one request, or returns `False` on timeout |

Create one `MqttConnection` and pass it to any number of stream writers, readers, requesters, and responders. After `await conn.connect()`, call `await reader.start()` or `await responder.start()` before traffic begins so their subscriptions are ready. Close each component with `await component.close()`, then call `conn.close()`. The connection is owned by the application, not by an individual writer or reader.

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
  -> MQTT adapter (one shared mqtt_as connection)
  -> broker
  -> desktop MAGPIE, another board, or another compatible peer
```

Only the MQTT adapter is included today. The core stream/RPC classes and serializer interface do not depend on MQTT. The implementation uses no worker thread or writer queue; readers and responders have bounded incoming mailboxes. RPC handlers run one at a time per responder, so long-running handlers should yield or be split into shorter work.

The default MQTT payload limit is 4096 bytes. Default stream and RPC publishes use QoS 1. ZeroMQ, WebRTC, audio/video frames, desktop-style CLI tools, and an HTTP MCP server are not included in this device package.

For an application with real devices, use your own broker and configure its authentication in `MQTT_CONFIG`. The public broker in these examples is for demonstrations.

---

## Examples and tests

| Example | Device behavior | Desktop companion |
|---|---|---|
| [Sensor stream](examples/mqtt_sensor_stream.py) | Publishes counter and free heap | `magpie-read-mqtt` |
| [User LED RPC](examples/mqtt_rpc_switch.py) | Responds to `on` and `off` requests | `magpie-request-mqtt` |
| [MCP tool](examples/mqtt_mcp_tool.py) | Exposes `free_memory` | `magpie-request-mqtt` or FastMCP `Client` |

The [example guide](examples/README.md) pairs every device script with working desktop commands. The [test guide](tests/README.md) covers host checks and ESP32 interoperability checks.

To run the host tests from this checkout, install `msgpack` on your computer and run:

```powershell
python -m pip install msgpack
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m unittest discover -s tests -p "test_*.py"
```

On Linux or macOS, use `PYTHONPATH=src python -m unittest discover -s tests -p 'test_*.py'`.

The host MQTT tests use an in-memory broker and need no board. Hardware tests use the board and broker described in [`tests/README.md`](tests/README.md).

---

## Related projects

| Project | Repository |
|---|---|
| MAGPIE for Python | [luxai-qtrobot/magpie](https://github.com/luxai-qtrobot/magpie) |
| MAGPIE.js | [luxai-qtrobot/magpie-js](https://github.com/luxai-qtrobot/magpie-js) |
| MAGPIE C++ | [luxai-qtrobot/magpie-cpp](https://github.com/luxai-qtrobot/magpie-cpp) |

## License

Licensed under the [GNU General Public License v3 (GPLv3)](LICENSE), matching desktop MAGPIE.
