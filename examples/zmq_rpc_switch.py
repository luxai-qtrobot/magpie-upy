"""Control the XIAO ESP32-S3 user LED over MAGPIE ZMQ RPC."""

import asyncio
import network
from machine import Pin

from luxai.magpie.transport.zmq import ZmqRpcResponder
from luxai.magpie.utils import Logger


DEVICE_ID = "esp32-001"
WIFI_SSID = "YOUR_WIFI"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"
PORT = 5558


led = Pin(21, Pin.OUT)
led.on()  # The user LED is active low, so GPIO high turns it off.


async def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        for _ in range(100):
            if wlan.isconnected():
                break
            await asyncio.sleep(0.2)
        else:
            raise OSError("Wi-Fi connection timed out")
    board_ip = wlan.ifconfig()[0]
    Logger.info(f"Wi-Fi connected: {board_ip}")
    return board_ip


def set_led_on_off(request):
    action = request.get("action") if isinstance(request, dict) else None
    if action not in ("on", "off"):
        return {"status": False, "error": "expected action 'on' or 'off'"}
    if action == "on":
        led.off()  # GPIO low lights the active-low LED.
    else:
        led.on()
    Logger.info(f"User LED: {action}")
    return {"status": True, "action": action}


async def main():
    board_ip = await connect_wifi()
    responder = ZmqRpcResponder(f"tcp://*:{PORT}")
    try:
        await responder.start()
        Logger.info(f"Serving {DEVICE_ID}/switch on tcp://{board_ip}:{PORT}")
        while True:
            await responder.respond(handler=set_led_on_off, timeout=1)
    finally:
        led.on()  # Leave the LED off when the example stops.
        await responder.close()


asyncio.run(main())
