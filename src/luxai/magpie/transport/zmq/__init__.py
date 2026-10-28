"""Optional ZMTP/TCP transport for MAGPIE on MicroPython."""

from .zmq_stream_writer import ZmqStreamWriter
from .zmq_stream_reader import ZmqStreamReader
from .zmq_rpc_requester import ZmqRpcRequester
from .zmq_rpc_responder import ZmqRpcResponder

# Keep the desktop Python spelling available as a small compatibility alias.
ZMQRpcRequester = ZmqRpcRequester
ZMQRpcResponder = ZmqRpcResponder

__all__ = (
    "ZmqStreamWriter", "ZmqStreamReader", "ZmqRpcRequester",
    "ZmqRpcResponder", "ZMQRpcRequester", "ZMQRpcResponder",
)
