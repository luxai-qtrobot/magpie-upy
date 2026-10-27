# Checks

Run the host checks from this repository root using a CPython environment with
`msgpack` installed and `src` on `PYTHONPATH`:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m unittest discover -s tests -p "test_*.py"
```

The host MQTT tests use an in-memory broker. No board or network is needed.

For the XIAO ESP32-S3 checks, install the package on the board, then run:

```powershell
mpremote connect COM13 run tests/device_codec_smoke.py
mpremote connect COM13 run tests/device_schema_smoke.py
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

