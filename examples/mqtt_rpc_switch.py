"""Control the XIAO ESP32-S3 user LED over MAGPIE MQTT RPC."""

import asyncio
from machine import Pin

from luxai.magpie.transport.mqtt import MqttConnection, MqttRpcResponder
from luxai.magpie.utils import Logger


DEVICE_ID = "esp32-001"  # Use a distinct ID for every board.

MQTT_CONFIG = {
    "ssid": "YOUR_WIFI",
    "wifi_pw": "YOUR_WIFI_PASSWORD",
    "server": "broker.hivemq.com",
    "port": 1883,
    "client_id": b"magpie-upy-esp32-001",  # Must be unique on the broker.
}


led = Pin(21, Pin.OUT)
led.on()  # GPIO high: the active-low user LED starts off.


def set_led_on_off(request):
    action = request.get("action") if isinstance(request, dict) else None
    if action not in ("on", "off"):
        return {"status": False, "error": "expected action 'on' or 'off'"}
    if action == "on":
        led.off()  # GPIO low turns the active-low LED on.
    else:
        led.on()  # GPIO high turns it off.
    Logger.info(f"User LED: {action}")
    return {"status": True, "action": action}


async def main():
    conn = MqttConnection(MQTT_CONFIG)
    responder = MqttRpcResponder(conn, service_name=f"{DEVICE_ID}/switch")
    try:
        await conn.connect()
        await responder.start()
        Logger.info(f"Serving user LED RPC on {DEVICE_ID}/switch")
        while True:
            await responder.respond(handler=set_led_on_off, timeout=1)
    finally:
        led.on()  # Leave the LED off when the example stops.
        await responder.close()
        conn.close()


asyncio.run(main())

