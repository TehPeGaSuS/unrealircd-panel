"""
unrealircd_rpc
~~~~~~~~~~~~~~
Python client library for the UnrealIRCd JSON-RPC interface.

Transport:  WebSocket (JSON-RPC 2.0)
Auth:       HTTP Basic at WS handshake

Quick start:
    from unrealircd_rpc import Manager, RPCError

    rpc = Manager.from_config({
        "host": "127.0.0.1",
        "port": 8600,
        "rpc_user": "webpanel",
        "rpc_password": "s3cret",
        "tls_verify": False,  # set True in production with real cert
    })

    # Simple query
    users = rpc.with_retry(lambda c: c.user().get_all())

    # Streaming logs (run in a background thread)
    stream = rpc.new_dedicated_client()
    stream.log().subscribe(["all", "!debug"])
    while True:
        event = stream.event_loop_recv(timeout=2.0)
        if event and isinstance(event, dict) and "msg" in event:
            print(event)
"""

from .connection import Connection, RPCError, ConnectionError, TimeoutError
from .manager import Manager
from . import audit

__all__ = [
    "Manager",
    "Connection",
    "RPCError",
    "ConnectionError",
    "TimeoutError",
    "audit",
]

__version__ = "0.1.0"
