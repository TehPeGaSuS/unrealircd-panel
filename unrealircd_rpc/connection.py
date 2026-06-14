"""
unrealircd_rpc.connection
~~~~~~~~~~~~~~~~~~~~~~~~~
Low-level WebSocket JSON-RPC 2.0 connection to UnrealIRCd.

Transport:  wss:// (or ws://) WebSocket
Auth:       HTTP Basic via Authorization header at handshake
Protocol:   JSON-RPC 2.0  {"jsonrpc":"2.0","method":"...","params":{},"id":N}

Supports:
  - Synchronous query/response (matched by id)
  - Async fire-and-forget (no_wait=True, used for rpc.set_issuer)
  - EventLoop mode for log streaming (dedicated connection only)
  - Automatic reconnection with error counting
"""

import base64
import json
import logging
import random
import threading
import time
from typing import Any, Optional

import websocket  # websocket-client

log = logging.getLogger(__name__)

# Error substrings that indicate a broken transport, not an application error.
_CONNECTION_ERROR_FRAGMENTS = (
    "websocket",
    "connection",
    "eof",
    "broken pipe",
    "reset by peer",
    "use of closed",
    "timed out",
    "timeout",
    "deadline",
    "i/o timeout",
    "network",
    "refused",
    "unreachable",
    "no route",
    "closed",
    "write:",
    "read:",
    "dial",
    "socket",
)


def _is_connection_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(frag in msg for frag in _CONNECTION_ERROR_FRAGMENTS)


class RPCError(Exception):
    """Raised when the server returns a JSON-RPC error object."""
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"RPC error {code}: {message}")


class ConnectionError(Exception):
    """Raised when the WebSocket transport fails."""


class TimeoutError(Exception):
    """Raised when a query times out waiting for a response."""


class Connection:
    """
    A single WebSocket connection to UnrealIRCd's JSON-RPC endpoint.

    Not thread-safe by itself — use Manager for concurrent access.

    Args:
        uri:        WebSocket URI, e.g. "wss://127.0.0.1:8600"
        api_login:  "rpc_user:password"
        tls_verify: Verify TLS certificate (default True)
        timeout:    Query timeout in seconds (default 10)
        issuer:     If set, sends rpc.set_issuer immediately after connect.
                    Do NOT set this on dedicated streaming connections.
    """

    def __init__(
        self,
        uri: str,
        api_login: str,
        tls_verify: bool = True,
        timeout: int = 10,
        issuer: Optional[str] = None,
    ):
        self.uri = uri
        self.api_login = api_login
        self.tls_verify = tls_verify
        self.timeout = timeout
        self.issuer = issuer
        self._ws: Optional[websocket.WebSocket] = None
        self._lock = threading.Lock()
        self._connect()

    # ------------------------------------------------------------------
    # Internal transport
    # ------------------------------------------------------------------

    def _build_headers(self) -> dict:
        encoded = base64.b64encode(self.api_login.encode()).decode()
        return {"Authorization": f"Basic {encoded}"}

    def _connect(self) -> None:
        sslopt = {} if self.tls_verify else {
            "cert_reqs": __import__("ssl").CERT_NONE,
            "check_hostname": False,
        }
        ws = websocket.WebSocket(sslopt=sslopt)
        ws.settimeout(self.timeout)
        try:
            ws.connect(self.uri, header=self._build_headers())
        except Exception as exc:
            raise ConnectionError(f"Failed to connect to {self.uri}: {exc}") from exc
        self._ws = ws
        log.debug("Connected to %s", self.uri)

        if self.issuer:
            # Fire-and-forget; don't wait for the reply — it's async and
            # waiting here would block before we're ready to receive.
            self._send_raw("rpc.set_issuer", {"name": self.issuer}, no_wait=True)

    def _send_raw(
        self,
        method: str,
        params: Optional[dict],
        no_wait: bool = False,
        req_id: Optional[int] = None,
    ) -> Optional[int]:
        if req_id is None:
            req_id = random.randint(1, 99_999)
        payload = json.dumps({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": req_id,
        })
        self._ws.send(payload)
        log.debug("→ %s (id=%s)", method, req_id)
        return None if no_wait else req_id

    def close(self) -> None:
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query(
        self,
        method: str,
        params: Optional[dict] = None,
        no_wait: bool = False,
    ) -> Any:
        """
        Send a JSON-RPC request and return the result.

        Args:
            method:   RPC method name, e.g. "user.list"
            params:   dict of parameters (or None)
            no_wait:  If True, send and return immediately (no reply read).
                      Used for rpc.set_issuer on connect.

        Returns:
            The "result" value from the JSON-RPC response.

        Raises:
            RPCError:        Server returned a JSON-RPC error.
            TimeoutError:    No response within self.timeout seconds.
            ConnectionError: Transport-level failure.
        """
        with self._lock:
            req_id = random.randint(1, 99_999)
            try:
                self._send_raw(method, params, no_wait=no_wait, req_id=req_id)
            except Exception as exc:
                raise ConnectionError(str(exc)) from exc

            if no_wait:
                return True

            deadline = time.monotonic() + self.timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Query '{method}' timed out after {self.timeout}s")

                try:
                    self._ws.settimeout(min(remaining, self.timeout))
                    raw = self._ws.recv()
                except websocket.WebSocketTimeoutException:
                    raise TimeoutError(f"Query '{method}' timed out")
                except Exception as exc:
                    raise ConnectionError(str(exc)) from exc

                try:
                    reply = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ConnectionError(f"Invalid JSON from server: {exc}") from exc

                reply_id = reply.get("id")

                # If the id doesn't match, this is a streaming event or the
                # async set_issuer ack — skip and keep waiting.
                if reply_id is not None and reply_id != req_id:
                    log.debug("← skipping id=%s (waiting for %s)", reply_id, req_id)
                    continue

                if "result" in reply:
                    log.debug("← %s ok", method)
                    return reply["result"]

                if "error" in reply:
                    err = reply["error"]
                    raise RPCError(err.get("code", -1), err.get("message", "unknown"))

                raise ConnectionError(f"Unexpected JSON-RPC response: {reply}")

    def event_loop_recv(self, timeout: float = 2.0) -> Optional[Any]:
        """
        Block up to `timeout` seconds for the next incoming frame.

        Used exclusively by dedicated streaming connections (log.subscribe).
        Returns None on timeout (caller should loop), raises on hard error.

        Note: Does NOT acquire _lock — only call from a single consumer thread.
        """
        try:
            self._ws.settimeout(timeout)
            raw = self._ws.recv()
        except websocket.WebSocketTimeoutException:
            return None
        except Exception as exc:
            raise ConnectionError(str(exc)) from exc

        try:
            reply = json.loads(raw)
        except json.JSONDecodeError:
            return None

        if "result" in reply:
            return reply["result"]
        if "error" in reply:
            err = reply["error"]
            log.warning("event_loop error: %s", err)
            return None
        return None

    # ------------------------------------------------------------------
    # Convenience namespace accessors
    # ------------------------------------------------------------------

    def user(self):
        from .namespaces import User
        return User(self)

    def channel(self):
        from .namespaces import Channel
        return Channel(self)

    def server(self):
        from .namespaces import Server
        return Server(self)

    def server_ban(self):
        from .namespaces import ServerBan
        return ServerBan(self)

    def server_ban_exception(self):
        from .namespaces import ServerBanException
        return ServerBanException(self)

    def name_ban(self):
        from .namespaces import NameBan
        return NameBan(self)

    def spamfilter(self):
        from .namespaces import Spamfilter
        return Spamfilter(self)

    def stats(self):
        from .namespaces import Stats
        return Stats(self)

    def log(self):
        from .namespaces import Log
        return Log(self)

    def message(self):
        from .namespaces import Message
        return Message(self)

    def rpc(self):
        from .namespaces import Rpc
        return Rpc(self)
