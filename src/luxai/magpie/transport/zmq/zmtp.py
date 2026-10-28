"""Small ZMTP 3.x TCP peer for MAGPIE's PUB/SUB and DEALER/ROUTER patterns."""

import asyncio
import socket
import struct


class ZmtpProtocolError(Exception):
    pass


def _property(name, value):
    if isinstance(value, str):
        value = value.encode()
    return bytes((len(name),)) + name + struct.pack(">I", len(value)) + value


def _properties(data):
    result = {}
    pos = 0
    while pos < len(data):
        size = data[pos]
        pos += 1
        if not size or pos + size + 4 > len(data):
            raise ZmtpProtocolError("invalid READY property")
        name = data[pos:pos + size].lower()
        pos += size
        value_size = struct.unpack(">I", data[pos:pos + 4])[0]
        pos += 4
        if value_size > len(data) - pos:
            raise ZmtpProtocolError("truncated READY property")
        result[name] = data[pos:pos + value_size]
        pos += value_size
    return result


class ZmtpPeer:
    """One TCP peer. The caller owns connection setup and reconnection."""

    _GREETING = b"\xff" + b"\x00" * 8 + b"\x7f\x03\x01" + b"NULL" + b"\x00" * 16 + b"\x00" * 32
    _PAIRS = {
        "PUB": ("SUB",),
        "SUB": ("PUB",),
        "DEALER": ("ROUTER",),
        "ROUTER": ("DEALER",),
    }

    def __init__(self, reader, writer, socket_type, identity=None,
                 max_frame_size=4096, max_message_size=8192, max_parts=8):
        if socket_type not in self._PAIRS:
            raise ValueError("unsupported ZMTP socket type")
        if max_frame_size < 1 or max_message_size < 1 or max_parts < 1:
            raise ValueError("ZMTP limits must be positive")
        self.reader = reader
        self.writer = writer
        try:
            writer.s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except (AttributeError, OSError):
            pass  # Some MicroPython ports do not expose TCP_NODELAY.
        self.socket_type = socket_type
        self.identity = identity.encode() if isinstance(identity, str) else (identity or b"")
        self.max_frame_size = max_frame_size
        self.max_message_size = max_message_size
        self.max_parts = max_parts
        self.remote_type = None
        self.remote_identity = b""
        self.minor = None
        self._write_lock = asyncio.Lock()
        self._closed = False

    async def handshake(self):
        # Sending before reading avoids deadlock with another symmetric peer.
        self.writer.write(self._GREETING)
        await self.writer.drain()
        greeting = await self.reader.readexactly(64)
        if (greeting[:1] != b"\xff" or greeting[9:11] != b"\x7f\x03"
                or greeting[12:32].rstrip(b"\x00") != b"NULL"
                or greeting[32] != 0 or greeting[11] not in (0, 1)):
            raise ZmtpProtocolError("unsupported ZMTP greeting")
        self.minor = min(self._GREETING[11], greeting[11])

        metadata = _property(b"Socket-Type", self.socket_type)
        if self.identity:
            metadata += _property(b"Identity", self.identity)
        await self.send_command(b"READY", metadata)
        flags, body = await self._read_frame()
        if flags != 4 or not body:
            raise ZmtpProtocolError("expected READY command")
        name_size = body[0]
        if not name_size or 1 + name_size > len(body):
            raise ZmtpProtocolError("invalid READY command")
        name = body[1:1 + name_size]
        if name == b"ERROR":
            raise ZmtpProtocolError("peer rejected ZMTP handshake")
        if name != b"READY":
            raise ZmtpProtocolError("expected READY command")
        metadata = _properties(body[1 + name_size:])
        remote = metadata.get(b"socket-type", b"")
        try:
            self.remote_type = remote.decode("ascii")
        except (UnicodeError, ValueError):
            raise ZmtpProtocolError("invalid peer socket type")
        if self.remote_type not in self._PAIRS[self.socket_type]:
            raise ZmtpProtocolError("incompatible peer socket type")
        self.remote_identity = metadata.get(b"identity", b"")
        return self.remote_type

    def _frame_header(self, flags, size):
        if size > self.max_frame_size:
            raise ZmtpProtocolError("ZMTP frame exceeds configured limit")
        if size < 256:
            return bytes((flags, size))
        return bytes((flags | 2,)) + struct.pack(">Q", size)

    async def _read_frame(self):
        flags = (await self.reader.readexactly(1))[0]
        if flags & ~7 or (flags & 4 and flags & 1):
            raise ZmtpProtocolError("invalid ZMTP frame flags")
        if flags & 2:
            size = struct.unpack(">Q", await self.reader.readexactly(8))[0]
        else:
            size = (await self.reader.readexactly(1))[0]
        if size > self.max_frame_size:
            raise ZmtpProtocolError("ZMTP frame exceeds configured limit")
        return flags, await self.reader.readexactly(size)

    async def send_command(self, name, data=b""):
        if isinstance(name, str):
            name = name.encode()
        body = bytes((len(name),)) + name + data
        header = self._frame_header(4, len(body))
        async with self._write_lock:
            self.writer.write(header)
            self.writer.write(body)
            await self.writer.drain()

    async def send_multipart(self, parts):
        if not parts or len(parts) > self.max_parts:
            raise ZmtpProtocolError("invalid ZMTP part count")
        total = 0
        for part in parts:
            total += len(part)
            if len(part) > self.max_frame_size or total > self.max_message_size:
                raise ZmtpProtocolError("ZMTP message exceeds configured limit")
        async with self._write_lock:
            last = len(parts) - 1
            for index, part in enumerate(parts):
                self.writer.write(self._frame_header(1 if index < last else 0, len(part)))
                if len(part) > 8192:
                    # MicroPython Stream.write buffers any unsent tail. Bound
                    # that buffer instead of handing it an entire image.
                    for offset in range(0, len(part), 8192):
                        self.writer.write(part[offset:offset + 8192])
                        await self.writer.drain()
                else:
                    self.writer.write(part)
            if len(parts[-1]) <= 8192:
                await self.writer.drain()

    async def subscribe(self, topic):
        if self.socket_type != "SUB" or self.minor is None:
            raise ZmtpProtocolError("SUB socket is not ready")
        if isinstance(topic, str):
            topic = topic.encode()
        if self.minor == 0:
            await self.send_multipart((b"\x01" + topic,))
        else:
            await self.send_command(b"SUBSCRIBE", topic)

    async def unsubscribe(self, topic):
        if self.socket_type != "SUB" or self.minor is None:
            raise ZmtpProtocolError("SUB socket is not ready")
        if isinstance(topic, str):
            topic = topic.encode()
        if self.minor == 0:
            await self.send_multipart((b"\x00" + topic,))
        else:
            await self.send_command(b"CANCEL", topic)

    async def recv_event(self):
        """Return ('message', parts) or ('subscribe'/'cancel', topic)."""
        if self.minor is None:
            raise ZmtpProtocolError("ZMTP handshake is incomplete")
        while True:
            flags, body = await self._read_frame()
            if flags & 4:
                if not body or not body[0] or 1 + body[0] > len(body):
                    raise ZmtpProtocolError("invalid ZMTP command")
                name = body[1:1 + body[0]]
                data = body[1 + body[0]:]
                if name == b"PING":
                    if len(data) < 2 or len(data) > 18:
                        raise ZmtpProtocolError("invalid ZMTP PING")
                    await self.send_command(b"PONG", data[2:])
                elif name == b"ERROR":
                    raise ZmtpProtocolError("peer reported ZMTP error")
                elif name in (b"SUBSCRIBE", b"CANCEL"):
                    return ("subscribe" if name == b"SUBSCRIBE" else "cancel", data)
                # PONG and unknown extension commands need no application action.
                continue

            parts = [body]
            total = len(body)
            if total > self.max_message_size:
                raise ZmtpProtocolError("ZMTP message exceeds configured limit")
            while flags & 1:
                if len(parts) >= self.max_parts:
                    raise ZmtpProtocolError("ZMTP message has too many parts")
                flags, body = await self._read_frame()
                if flags & 4:
                    raise ZmtpProtocolError("command inside multipart message")
                total += len(body)
                if total > self.max_message_size:
                    raise ZmtpProtocolError("ZMTP message exceeds configured limit")
                parts.append(body)
            # ZMTP 3.0 represents subscriptions as ordinary one-part messages.
            if (self.socket_type == "PUB" and self.remote_type == "SUB"
                    and len(parts) == 1 and parts[0][:1] in (b"\x00", b"\x01")):
                return ("subscribe" if parts[0][0] else "cancel", parts[0][1:])
            return "message", parts

    async def close(self):
        if not self._closed:
            self._closed = True
            self.writer.close()
        # MicroPython's Stream.close() alone does not close the TCP socket.
        # wait_closed() performs the actual close there.
        if hasattr(self.writer, "wait_closed"):
            try:
                await self.writer.wait_closed()
            except OSError:
                pass
            finally:
                # Also close on cancellation during wait_closed(). CPython's
                # StreamWriter has no .s; MicroPython's Stream does.
                if hasattr(self.writer, "s"):
                    try:
                        self.writer.s.close()
                    except OSError:
                        pass
