# Checks

Run the host checks from this repository root using a CPython environment with
`msgpack` and `pyzmq` installed and `src` on `PYTHONPATH`:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m unittest discover -s tests -p "test_*.py"
```

The host MQTT tests use an in-memory broker. The ZMQ tests exchange real TCP
frames with PyZMQ over loopback. Neither needs a board.

For the XIAO ESP32-S3 checks, install the default `package.json` from the
repository root on the board, then run:

```powershell
mpremote connect COM13 mip install package.json
mpremote connect COM13 run tests/device_codec_smoke.py
mpremote connect COM13 run tests/device_schema_smoke.py
```

For the hardware MQTT tests, install the optional MQTT manifest too:

```powershell
mpremote connect COM13 mip install package-mqtt.json
```

The hardware MQTT test scripts still use a board-side `secrets.py`, separate
from the runnable examples. Create an untracked `secrets.py` with `MQTT_CONFIG`
using the same keys shown in an example, then copy it to `:secrets.py` on the
board:

```powershell
mpremote connect COM13 fs cp secrets.py :secrets.py
```

Run `device_mqtt_smoke.py`; after it prints `device_ready`, run
`host_mqtt_smoke.py` from a desktop MAGPIE Python environment. Both scripts use
`broker.hivemq.com` and a shared test topic, so they require internet access.
They check stream payloads, a Frame, raw RPC, and MCP initialize/list/call.
Use a distinct MQTT client ID for the board. Replace `COM13` with your port.

For the full MCP client path, run `examples/mqtt_mcp_tool.py` on the board and
then `host_fastmcp_smoke.py` in a desktop Python environment with MAGPIE and
FastMCP installed. It discovers and invokes the board's `free_memory` tool.

To check an ESP32 requester, start `host_responder_smoke.py` on the desktop,
then run `device_requester_smoke.py` on the board. These two scripts verify the
request, ACK, and final reply in the other direction.

For ZMQ hardware checks, install the default `package.json` and copy a `secrets.py`
containing `MQTT_CONFIG["ssid"]` and `MQTT_CONFIG["wifi_pw"]` to the board.
These keys supply Wi-Fi credentials only; the ZMQ transport does not use MQTT.
Run `device_zmq_smoke.py`, note the printed board IP, and run the host check
from a desktop environment with `pyzmq` and `msgpack`:

```powershell
mpremote connect COM13 mip install package.json
mpremote connect COM13 run tests/device_zmq_smoke.py
python tests/host_device_zmq_smoke.py BOARD_IP
```

The first ZMQ check covers a board PUB stream and a board ROUTER MCP tool.
For the reverse stream direction, run the second board script and publish to
its bound SUB socket from desktop MAGPIE:

```powershell
mpremote connect COM13 run tests/device_zmq_client_smoke.py
magpie-write.exe tcp://BOARD_IP:58675 magpie-upy/zmq/input "{'from':'desktop','n':7}" --raw --rate 5 --count 20
```

The second board script also checks DEALER request/ACK/reply against a local
ROUTER on the board. Run each board script and its desktop command in separate
terminals.

