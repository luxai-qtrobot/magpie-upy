"""One mqtt_as client shared by MAGPIE streams and RPC services."""

import binascii
import os


def _hex_random(count=6):
    return binascii.hexlify(os.urandom(count)).decode()


def _matches(pattern, topic):
    """Match MQTT + and # subscriptions without allocating a regex."""
    parts = pattern.split("/")
    levels = topic.split("/")
    for index, part in enumerate(parts):
        if part == "#":
            return index == len(parts) - 1
        if index >= len(levels) or (part != "+" and part != levels[index]):
            return False
    return len(parts) == len(levels)


class MqttConnection:
    """Shared MQTT 3.1.1 connection.

    Pass mqtt_as configuration keys (ssid, wifi_pw, server, port, user, ...)
    in *config*. The caller owns this connection; closing a writer or reader
    never closes it. ``client`` allows host tests without importing mqtt_as.
    """

    def __init__(self, config=None, client=None, max_payload=4096, max_publishes=4):
        if client is None:
            from mqtt_as import MQTTClient, config as mqtt_defaults
            settings = dict(mqtt_defaults)
            if config:
                settings.update(config)
        else:
            settings = dict(config or {})
        client_id = settings.get("client_id")
        if not client_id:
            client_id = "magpie-upy-" + _hex_random(4)
        if isinstance(client_id, bytes):
            client_id = client_id.decode()
        self.client_id = client_id
        settings["client_id"] = client_id.encode()
        settings["subs_cb"] = self._on_message
        settings["connect_coro"] = self._on_connect
        self._client = client if client is not None else MQTTClient(settings)
        self._subscriptions = {}  # pattern -> [callbacks]
        self._subscription_qos = {}
        self._connected = False
        self._subscribed_once = False
        self._closed = False
        self._max_payload = max_payload
        self._max_publishes = max_publishes
        self._publishing = 0
        self.dropped_messages = 0
        self.callback_errors = 0
        # A fake client can read the same settings and invoke the callbacks.
        self.config = settings

    async def _on_connect(self, client):
        self._connected = True
        self._subscribed_once = True
        for topic in tuple(self._subscriptions):
            await client.subscribe(topic, self._subscription_qos[topic])

    def _on_message(self, topic, payload, retained=False, properties=None):
        if self._closed:
            return
        if isinstance(topic, (bytes, bytearray)):
            topic = topic.decode()
        if len(payload) > self._max_payload:
            self.dropped_messages += 1
            return
        # mqtt_as may reuse its receive buffer; subscribers must own these bytes.
        payload = bytes(payload)
        for pattern, callbacks in self._subscriptions.items():
            if _matches(pattern, topic):
                for callback in callbacks:
                    try:
                        callback(payload, topic)
                    except Exception:
                        self.callback_errors += 1

    async def connect(self):
        if self._closed:
            raise RuntimeError("MQTT connection is closed")
        await self._client.connect()
        self._connected = True
        # mqtt_as normally invokes connect_coro. Support fake clients and
        # drivers that only invoke it after a later reconnect.
        if not self._subscribed_once:
            await self._on_connect(self._client)
        return self

    async def add_subscription(self, topic, callback, qos=1):
        if self._closed:
            raise RuntimeError("MQTT connection is closed")
        if not topic:
            raise ValueError("topic is required")
        callbacks = self._subscriptions.get(topic)
        if callbacks is None:
            callbacks = []
            self._subscriptions[topic] = callbacks
            self._subscription_qos[topic] = qos
            if self._connected:
                try:
                    await self._client.subscribe(topic, qos)
                except Exception:
                    del self._subscriptions[topic]
                    del self._subscription_qos[topic]
                    raise
        elif qos > self._subscription_qos[topic]:
            if self._connected:
                await self._client.subscribe(topic, qos)
            self._subscription_qos[topic] = qos
        if callback not in callbacks:
            callbacks.append(callback)

    async def remove_subscription(self, topic, callback):
        callbacks = self._subscriptions.get(topic)
        if callbacks is None:
            return
        if callback in callbacks:
            callbacks.remove(callback)
        if not callbacks:
            del self._subscriptions[topic]
            del self._subscription_qos[topic]
            if self._connected and not self._closed:
                await self._client.unsubscribe(topic)

    async def publish(self, topic, payload, qos=1, retain=False):
        if self._closed:
            raise RuntimeError("MQTT connection is closed")
        if not topic:
            raise ValueError("topic is required")
        if len(payload) > self._max_payload:
            raise ValueError("MQTT payload exceeds configured limit")
        if self._publishing >= self._max_publishes:
            raise RuntimeError("too many MQTT publishes in progress")
        self._publishing += 1
        try:
            await self._client.publish(topic, payload, qos=qos, retain=retain)
        finally:
            self._publishing -= 1

    def close(self):
        if not self._closed:
            self._closed = True
            self._connected = False
            self._subscriptions.clear()
            self._subscription_qos.clear()
            self._client.close()


class _Mailbox:
    """Tiny bounded FIFO for a callback producer and an async reader."""

    def __init__(self, limit, drop_oldest=False):
        import asyncio
        if limit < 1:
            raise ValueError("mailbox limit must be positive")
        self._items = []
        self._limit = limit
        self._drop_oldest = drop_oldest
        self._ready = asyncio.Event()
        self._closed = False
        self.dropped = 0

    def put(self, item):
        if self._closed:
            return False
        if len(self._items) >= self._limit:
            self.dropped += 1
            if not self._drop_oldest:
                return False
            self._items.pop(0)
        self._items.append(item)
        self._ready.set()
        return True

    async def get(self, timeout=None):
        import asyncio
        while not self._items:
            if self._closed:
                raise RuntimeError("mailbox is closed")
            self._ready.clear()
            try:
                if timeout is None:
                    await self._ready.wait()
                else:
                    await asyncio.wait_for(self._ready.wait(), timeout)
            except asyncio.TimeoutError:
                raise asyncio.TimeoutError("no MQTT message received")
        return self._items.pop(0)

    def close(self):
        self._closed = True
        self._items.clear()
        self._ready.set()

