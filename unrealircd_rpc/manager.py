"""
unrealircd_rpc.manager
~~~~~~~~~~~~~~~~~~~~~~
Thread-safe connection manager with automatic reconnection.

Mirrors the v2 Go Manager design:
  - Singleton (or per-app-instance) manager
  - with_retry() wraps any RPC call with reconnect-on-failure
  - new_dedicated_client() for streaming (no issuer, separate connection)
  - Error counting: after 2 failures, proactively reconnects before next call

Usage (Flask context):
    from unrealircd_rpc import Manager

    rpc = Manager.from_config({
        "host": "127.0.0.1",
        "port": 8600,
        "rpc_user": "webpanel",
        "rpc_password": "secret",
        "tls_verify": True,
    })

    # In a route:
    users = rpc.with_retry(lambda c: c.user().get_all())

    # Streaming (in a background thread):
    stream = rpc.new_dedicated_client()
    stream.log().subscribe(["all"])
    while True:
        event = stream.event_loop_recv()
        if event:
            ...  # push to SSE broker
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional

from .connection import Connection, ConnectionError, _is_connection_error

log = logging.getLogger(__name__)


class _ServerConfig:
    """Holds the credentials needed to (re)connect."""

    def __init__(
        self,
        host: str,
        port: int,
        rpc_user: str,
        rpc_password: str,
        tls_verify: bool = True,
        timeout: int = 10,
    ):
        self.host = host
        self.port = port
        self.rpc_user = rpc_user
        self.rpc_password = rpc_password
        self.tls_verify = tls_verify
        self.timeout = timeout

    @property
    def uri(self) -> str:
        scheme = "wss" if self.tls_verify or True else "ws"
        return f"{scheme}://{self.host}:{self.port}"

    @property
    def api_login(self) -> str:
        return f"{self.rpc_user}:{self.rpc_password}"


class _ManagedClient:
    """A Connection plus error-tracking metadata."""

    def __init__(self, conn: Connection, config: _ServerConfig, issuer: str):
        self.conn = conn
        self.config = config
        self.issuer = issuer
        self._error_count: int = 0
        self._last_error: Optional[float] = None
        self._last_success: Optional[float] = None
        self._lock = threading.Lock()

    def record_error(self) -> bool:
        """Record a failure. Returns True if reconnect is recommended."""
        with self._lock:
            self._error_count += 1
            self._last_error = time.monotonic()
            return self._error_count >= 2

    def record_success(self) -> None:
        with self._lock:
            self._error_count = 0
            self._last_success = time.monotonic()

    def needs_reconnect(self) -> bool:
        with self._lock:
            if self._error_count >= 2:
                return True
            if self._last_error and (
                self._last_success is None or self._last_success < self._last_error
            ):
                return (time.monotonic() - self._last_error) < 30
            return False


class Manager:
    """
    Thread-safe manager for one or more UnrealIRCd RPC connections.

    For UnrealIRCd (single server), just use from_config() and keep one Manager
    per Flask app (store it in app.extensions or a module-level variable).
    """

    def __init__(self):
        self._clients: dict[str, _ManagedClient] = {}
        self._active: Optional[str] = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: dict, issuer: str = "webpanel") -> "Manager":
        """
        Create a Manager and immediately connect.

        config keys:
            host, port, rpc_user, rpc_password
            tls_verify  (bool, default True)
            timeout     (int seconds, default 10)
            name        (str, default "default")

        Raises ConnectionError if initial connect fails.
        """
        m = cls()
        m.connect(config, issuer=issuer)
        return m

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self, config: dict, issuer: str = "webpanel") -> _ManagedClient:
        """Connect to a server and register it as active."""
        srv = _ServerConfig(
            host=config["host"],
            port=int(config["port"]),
            rpc_user=config["rpc_user"],
            rpc_password=config["rpc_password"],
            tls_verify=config.get("tls_verify", True),
            timeout=config.get("timeout", 10),
        )
        name = config.get("name", "default")

        with self._lock:
            if name in self._clients:
                log.debug("Already connected to %s, reusing", name)
                return self._clients[name]

            conn = Connection(
                uri=srv.uri,
                api_login=srv.api_login,
                tls_verify=srv.tls_verify,
                timeout=srv.timeout,
                issuer=issuer,
            )
            client = _ManagedClient(conn, srv, issuer)
            self._clients[name] = client
            if self._active is None:
                self._active = name

            log.info("Connected to UnrealIRCd RPC at %s (name=%s)", srv.uri, name)
            return client

    def disconnect(self, name: str = "default") -> None:
        with self._lock:
            client = self._clients.pop(name, None)
            if client:
                client.conn.close()
                log.info("Disconnected from %s", name)
            if self._active == name:
                self._active = next(iter(self._clients), None)

    def _reconnect(self, name: str) -> _ManagedClient:
        """Replace the named client with a fresh connection."""
        with self._lock:
            old = self._clients.get(name)
            if old:
                try:
                    old.conn.close()
                except Exception:
                    pass

            cfg = old.config if old else None
            iss = old.issuer if old else "webpanel"
            if cfg is None:
                raise ConnectionError(f"No config stored for server '{name}'")

            log.info("Reconnecting to %s...", name)
            conn = Connection(
                uri=cfg.uri,
                api_login=cfg.api_login,
                tls_verify=cfg.tls_verify,
                timeout=cfg.timeout,
                issuer=iss,
            )
            client = _ManagedClient(conn, cfg, iss)
            self._clients[name] = client
            log.info("Reconnected to %s", name)
            return client

    # ------------------------------------------------------------------
    # Client access
    # ------------------------------------------------------------------

    def get_active(self) -> _ManagedClient:
        with self._lock:
            if not self._active or self._active not in self._clients:
                raise ConnectionError("No active RPC connection")
            return self._clients[self._active]

    def get_active_conn(self) -> Connection:
        return self.get_active().conn

    def set_active(self, name: str) -> None:
        with self._lock:
            if name not in self._clients:
                raise ValueError(f"Not connected to '{name}'")
            self._active = name

    def list_connections(self) -> list[str]:
        with self._lock:
            return list(self._clients.keys())

    # ------------------------------------------------------------------
    # with_retry  (the main call pattern for Flask routes)
    # ------------------------------------------------------------------

    def with_retry(self, fn: Callable[[Connection], Any]) -> Any:
        """
        Execute fn(conn) with automatic reconnection on transport errors.

        Usage:
            result = rpc.with_retry(lambda c: c.user().get_all())

        - On first call, uses the active connection.
        - If a connection error is detected (or error count >= 2),
          reconnects and retries fn once.
        - Application-level RPCErrors are NOT retried — they propagate.

        Raises:
            ConnectionError: if reconnect also fails
            RPCError:        if the server returns an application error
        """
        with self._lock:
            active_name = self._active

        if not active_name:
            raise ConnectionError("No active RPC connection")

        # Proactive reconnect if we've been having trouble
        try:
            client = self.get_active()
            if client.needs_reconnect():
                log.info("Proactively reconnecting due to recent errors...")
                client = self._reconnect(active_name)
        except ConnectionError:
            client = self._reconnect(active_name)

        try:
            result = fn(client.conn)
            client.record_success()
            return result
        except Exception as exc:
            should_reconnect = client.record_error()

            if _is_connection_error(exc) or should_reconnect:
                log.warning("RPC connection error (%s), attempting reconnect...", exc)
                try:
                    new_client = self._reconnect(active_name)
                except Exception as reconnect_exc:
                    raise ConnectionError(
                        f"Connection lost: {exc}; reconnect failed: {reconnect_exc}"
                    ) from exc

                try:
                    result = fn(new_client.conn)
                    new_client.record_success()
                    return result
                except Exception:
                    raise  # Don't retry a second time

            raise  # Non-connection error, propagate as-is

    # ------------------------------------------------------------------
    # Dedicated streaming client
    # ------------------------------------------------------------------

    def new_dedicated_client(self) -> Connection:
        """
        Create a fresh, unshared Connection for log streaming.

        Key differences from the main connection:
          - NOT stored in self._clients (unmanaged, caller owns it)
          - Does NOT set issuer — the async set_issuer ack would corrupt
            the EventLoop frame stream (same gotcha as in v2 Go code)
          - Caller must call conn.close() when done

        Usage:
            stream = rpc.new_dedicated_client()
            stream.log().subscribe(["all"])
            while not stop_event.is_set():
                event = stream.event_loop_recv(timeout=2.0)
                if event and "msg" in event:
                    sse_broker.publish(event)
            stream.close()
        """
        with self._lock:
            active_name = self._active
            if not active_name or active_name not in self._clients:
                raise ConnectionError("No active RPC connection to base streaming client on")
            cfg = self._clients[active_name].config

        log.info("Creating dedicated streaming connection to %s", cfg.uri)
        return Connection(
            uri=cfg.uri,
            api_login=cfg.api_login,
            tls_verify=cfg.tls_verify,
            timeout=cfg.timeout,
            issuer=None,  # intentionally omitted for streaming
        )

    # ------------------------------------------------------------------
    # Convenience: test a connection without storing it
    # ------------------------------------------------------------------

    @staticmethod
    def test_connection(config: dict) -> None:
        """
        Attempt to connect and call rpc.info.
        Raises ConnectionError or RPCError on failure.
        Used by settings UI to verify credentials before saving.
        """
        srv = _ServerConfig(
            host=config["host"],
            port=int(config["port"]),
            rpc_user=config["rpc_user"],
            rpc_password=config["rpc_password"],
            tls_verify=config.get("tls_verify", True),
        )
        conn = Connection(uri=srv.uri, api_login=srv.api_login, tls_verify=srv.tls_verify)
        try:
            conn.query("rpc.info")
        finally:
            conn.close()
