"""
unrealircd_rpc.namespaces
~~~~~~~~~~~~~~~~~~~~~~~~~
One class per UnrealIRCd RPC namespace, each wrapping conn.query().

Method names mirror the PHP library where possible, with Pythonic naming
(get_all, set_nick, etc.).  Parameters are passed as keyword args and
assembled into the params dict internally.

object_detail_level:
    0 = minimal
    1 = basic  (use for lists — fast)
    2 = medium
    4 = full   (use for single-item fetches)
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from .connection import Connection


class _Namespace:
    def __init__(self, conn: "Connection"):
        self._conn = conn

    def _q(self, method: str, params: Optional[dict] = None) -> Any:
        return self._conn.query(method, params)


# ---------------------------------------------------------------------------
# rpc.*
# ---------------------------------------------------------------------------

class Rpc(_Namespace):
    def info(self) -> Any:
        """List all loaded RPC modules."""
        return self._q("rpc.info")

    def set_issuer(self, name: str) -> bool:
        """
        Tag subsequent RPC calls with a display name (e.g. logged-in panel user).
        Fires async — no reply is awaited.
        Requires UnrealIRCd 6.0.8+.
        """
        return self._conn.query("rpc.set_issuer", {"name": name}, no_wait=True)

    def add_timer(
        self,
        timer_id: str,
        every_msec: int,
        method: str,
        params: Optional[dict] = None,
    ) -> Any:
        """Schedule a repeating RPC call server-side. Requires 6.1.0+."""
        import random
        inner_id = random.randint(100_000, 999_999)
        return self._q("rpc.add_timer", {
            "timer_id": timer_id,
            "every_msec": every_msec,
            "request": {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": inner_id,
            },
        })

    def del_timer(self, timer_id: str) -> Any:
        return self._q("rpc.del_timer", {"timer_id": timer_id})


# ---------------------------------------------------------------------------
# stats.*
# ---------------------------------------------------------------------------

class Stats(_Namespace):
    def get(self, object_detail_level: int = 1) -> Any:
        """
        Basic network stats.

        Response shape:
          {
            "server":     {"total": N},
            "user":       {"total": N, "oper": N},
            "channel":    {"total": N},
            "server_ban": {"total": N},
          }
        """
        return self._q("stats.get", {"object_detail_level": object_detail_level})

    def parse(self, result: dict) -> dict:
        """
        Parse a stats.get result into a flat, friendly dict.
        Convenience helper — avoids duplicating the nested key logic everywhere.
        """
        out = {
            "users": 0,
            "opers": 0,
            "channels": 0,
            "servers": 0,
            "server_bans": 0,
        }
        if not isinstance(result, dict):
            return out
        if srv := result.get("server"):
            out["servers"] = srv.get("total", 0)
        if usr := result.get("user"):
            out["users"] = usr.get("total", 0)
            out["opers"] = usr.get("oper", 0)
        if ch := result.get("channel"):
            out["channels"] = ch.get("total", 0)
        if ban := result.get("server_ban"):
            out["server_bans"] = ban.get("total", 0)
        return out


# ---------------------------------------------------------------------------
# user.*
# ---------------------------------------------------------------------------

class User(_Namespace):
    def get_all(self, object_detail_level: int = 2) -> List[Any]:
        result = self._q("user.list", {"object_detail_level": object_detail_level})
        return result.get("list", []) if isinstance(result, dict) else []

    def get(self, nick: str, object_detail_level: int = 4) -> Optional[Any]:
        result = self._q("user.get", {
            "nick": nick,
            "object_detail_level": object_detail_level,
        })
        return result.get("client") if isinstance(result, dict) else None

    def set_nick(self, nick: str, newnick: str) -> Any:
        return self._q("user.set_nick", {"nick": nick, "newnick": newnick})

    def set_username(self, nick: str, username: str) -> Any:
        return self._q("user.set_username", {"nick": nick, "username": username})

    def set_realname(self, nick: str, realname: str) -> Any:
        return self._q("user.set_realname", {"nick": nick, "realname": realname})

    def set_vhost(self, nick: str, vhost: str) -> Any:
        return self._q("user.set_vhost", {"nick": nick, "vhost": vhost})

    def set_mode(self, nick: str, modes: str, hidden: bool = False) -> Any:
        return self._q("user.set_mode", {"nick": nick, "modes": modes, "hidden": hidden})

    def set_snomask(self, nick: str, snomask: str, hidden: bool = False) -> Any:
        return self._q("user.set_snomask", {"nick": nick, "snomask": snomask, "hidden": hidden})

    def set_oper(
        self,
        nick: str,
        oper_account: str,
        oper_class: str,
        class_: Optional[str] = None,
        modes: Optional[str] = None,
        snomask: Optional[str] = None,
        vhost: Optional[str] = None,
    ) -> Any:
        return self._q("user.set_oper", {
            "nick": nick,
            "oper_account": oper_account,
            "oper_class": oper_class,
            "class": class_,
            "modes": modes,
            "snomask": snomask,
            "vhost": vhost,
        })

    def join(
        self,
        nick: str,
        channel: str,
        key: Optional[str] = None,
        force: bool = False,
    ) -> Any:
        return self._q("user.join", {"nick": nick, "channel": channel, "key": key, "force": force})

    def part(self, nick: str, channel: str, force: bool = False) -> Any:
        return self._q("user.part", {"nick": nick, "channel": channel, "force": force})

    def quit(self, nick: str, reason: str) -> Any:
        return self._q("user.quit", {"nick": nick, "reason": reason})

    def kill(self, nick: str, reason: str) -> Any:
        return self._q("user.kill", {"nick": nick, "reason": reason})


# ---------------------------------------------------------------------------
# channel.*
# ---------------------------------------------------------------------------

class Channel(_Namespace):
    def get_all(self, object_detail_level: int = 1) -> List[Any]:
        result = self._q("channel.list", {"object_detail_level": object_detail_level})
        return result.get("list", []) if isinstance(result, dict) else []

    def get(self, channel: str, object_detail_level: int = 3) -> Optional[Any]:
        result = self._q("channel.get", {
            "channel": channel,
            "object_detail_level": object_detail_level,
        })
        return result.get("channel") if isinstance(result, dict) else None

    def set_mode(self, channel: str, modes: str, parameters: str = "") -> Any:
        return self._q("channel.set_mode", {
            "channel": channel,
            "modes": modes,
            "parameters": parameters,
        })

    def set_topic(
        self,
        channel: str,
        topic: str,
        set_by: Optional[str] = None,
        set_at: Optional[str] = None,
    ) -> Any:
        return self._q("channel.set_topic", {
            "channel": channel,
            "topic": topic,
            "set_by": set_by,
            "set_at": set_at,
        })

    def kick(self, channel: str, nick: str, reason: str) -> Any:
        return self._q("channel.kick", {"nick": nick, "channel": channel, "reason": reason})


# ---------------------------------------------------------------------------
# server.*
# ---------------------------------------------------------------------------

class Server(_Namespace):
    def get_all(self, object_detail_level: int = 3) -> List[Any]:
        result = self._q("server.list", {"object_detail_level": object_detail_level})
        return result.get("list", []) if isinstance(result, dict) else []

    def get(self, server: Optional[str] = None, object_detail_level: int = 3) -> Optional[Any]:
        result = self._q("server.get", {"server": server, "object_detail_level": object_detail_level})
        return result.get("server") if isinstance(result, dict) else None

    def rehash(self, server: str) -> Any:
        return self._q("server.rehash", {"server": server})

    def connect(self, link: str) -> Any:
        return self._q("server.connect", {"link": link})

    def disconnect(self, link: str, reason: str = "No reason") -> Any:
        return self._q("server.disconnect", {"link": link, "reason": reason})

    def module_list(self, server: Optional[str] = None) -> Any:
        params = {}
        if server:
            params["server"] = server
        return self._q("server.module_list", params or None)


# ---------------------------------------------------------------------------
# server_ban.*
# ---------------------------------------------------------------------------

class ServerBan(_Namespace):
    def get_all(self) -> List[Any]:
        result = self._q("server_ban.list")
        return result.get("list", []) if isinstance(result, dict) else []

    def get(self, name: str, type_: str) -> Optional[Any]:
        result = self._q("server_ban.get", {"name": name, "type": type_})
        return result.get("tkl") if isinstance(result, dict) else None

    def add(
        self,
        name: str,
        type_: str,
        duration: str,
        reason: str,
    ) -> Optional[Any]:
        """
        Add a server ban.

        Args:
            name:     Target (e.g. "*@1.2.3.4" or "*@*.badhost.com")
            type_:    Ban type: "gline", "kline", "zline", "gzline", "shun", "eline"
            duration: Duration string e.g. "1d", "2w", "0" (permanent)
            reason:   Ban reason
        """
        result = self._q("server_ban.add", {
            "name": name,
            "type": type_,
            "reason": reason,
            "duration_string": duration,
        })
        return result.get("tkl") if isinstance(result, dict) else None

    def delete(self, name: str, type_: str) -> Optional[Any]:
        result = self._q("server_ban.del", {"name": name, "type": type_})
        return result.get("tkl") if isinstance(result, dict) else None


# ---------------------------------------------------------------------------
# server_ban_exception.*
# ---------------------------------------------------------------------------

class ServerBanException(_Namespace):
    def get_all(self) -> List[Any]:
        result = self._q("server_ban_exception.list", {})
        return result.get("list", []) if isinstance(result, dict) else []

    def get(self, name: str) -> Optional[Any]:
        result = self._q("server_ban_exception.get", {"name": name})
        return result.get("tkl") if isinstance(result, dict) else None

    def add(
        self,
        name: str,
        exception_types: str,
        reason: str,
        set_by: Optional[str] = None,
        duration: Optional[str] = None,
    ) -> Optional[Any]:
        params: dict = {"name": name, "exception_types": exception_types, "reason": reason}
        if set_by:
            params["set_by"] = set_by
        if duration:
            params["duration_string"] = duration
        result = self._q("server_ban_exception.add", params)
        return result.get("tkl") if isinstance(result, dict) else None

    def delete(self, name: str) -> Optional[Any]:
        result = self._q("server_ban_exception.del", {"name": name})
        return result.get("tkl") if isinstance(result, dict) else None


# ---------------------------------------------------------------------------
# name_ban.*  (QLines)
# ---------------------------------------------------------------------------

class NameBan(_Namespace):
    def get_all(self) -> List[Any]:
        result = self._q("name_ban.list")
        return result.get("list", []) if isinstance(result, dict) else []

    def get(self, name: str) -> Optional[Any]:
        result = self._q("name_ban.get", {"name": name})
        return result.get("tkl") if isinstance(result, dict) else None

    def add(
        self,
        name: str,
        reason: str,
        duration: str = "0",
        set_by: Optional[str] = None,
    ) -> Optional[Any]:
        params: dict = {"name": name, "reason": reason, "duration_string": duration}
        if set_by:
            params["set_by"] = set_by
        result = self._q("name_ban.add", params)
        return result.get("tkl") if isinstance(result, dict) else None

    def delete(self, name: str) -> Optional[Any]:
        result = self._q("name_ban.del", {"name": name})
        return result.get("tkl") if isinstance(result, dict) else None


# ---------------------------------------------------------------------------
# spamfilter.*
# ---------------------------------------------------------------------------

class Spamfilter(_Namespace):
    def get_all(self) -> List[Any]:
        result = self._q("spamfilter.list")
        return result.get("list", []) if isinstance(result, dict) else []

    def get(
        self,
        name: str,
        match_type: str,
        spamfilter_targets: str,
        ban_action: str,
    ) -> Optional[Any]:
        result = self._q("spamfilter.get", {
            "name": name,
            "match_type": match_type,
            "spamfilter_targets": spamfilter_targets,
            "ban_action": ban_action,
        })
        return result.get("tkl") if isinstance(result, dict) else None

    def add(
        self,
        name: str,
        match_type: str,
        spamfilter_targets: str,
        ban_action: str,
        ban_duration: str,
        reason: str,
    ) -> Optional[Any]:
        """
        Args:
            match_type:          "simple", "regex", "extended"
            spamfilter_targets:  e.g. "p" (privmsg), "cpnNPq", "all"
            ban_action:          "gline", "kill", "block", "dccblock", etc.
            ban_duration:        e.g. "1d", "0" (permanent)
        """
        result = self._q("spamfilter.add", {
            "name": name,
            "match_type": match_type,
            "spamfilter_targets": spamfilter_targets,
            "ban_action": ban_action,
            "ban_duration": ban_duration,
            "reason": reason,
        })
        return result.get("tkl") if isinstance(result, dict) else None

    def delete(
        self,
        name: str,
        match_type: str,
        spamfilter_targets: str,
        ban_action: str,
    ) -> Optional[Any]:
        result = self._q("spamfilter.del", {
            "name": name,
            "match_type": match_type,
            "spamfilter_targets": spamfilter_targets,
            "ban_action": ban_action,
        })
        return result.get("tkl") if isinstance(result, dict) else None


# ---------------------------------------------------------------------------
# log.*
# ---------------------------------------------------------------------------

class Log(_Namespace):
    def subscribe(self, sources: List[str]) -> Any:
        """
        Subscribe to live log events.

        IMPORTANT: After calling this, use conn.event_loop_recv() in a loop
        to receive events.  Do NOT use conn.query() on the same connection —
        use a dedicated connection for streaming.

        Args:
            sources: e.g. ["all"], ["!debug", "all"], ["connect", "disconnect"]
        """
        return self._q("log.subscribe", {"sources": sources})

    def unsubscribe(self) -> Any:
        return self._q("log.unsubscribe")

    def get_all(self, sources: Optional[List[str]] = None) -> List[Any]:
        """Fetch past log events from the server's in-memory buffer."""
        result = self._q("log.list", {"sources": sources})
        return result.get("list", []) if isinstance(result, dict) else []

    def send(
        self,
        message: str,
        level: str = "info",
        subsystem: str = "webpanel",
        event_id: str = "WEBPANEL_EVENT",
    ) -> Any:
        """
        Inject a log entry into UnrealIRCd's log system.

        This is how the panel writes audit events — they appear alongside
        IRC events in UnrealIRCd's own logs.

        Args:
            level:     "info", "warn", "error"
            subsystem: appears as the source tag in logs
            event_id:  all-caps event identifier, e.g. "WEBPANEL_LOGIN"
        """
        return self._q("log.send", {
            "level": level,
            "subsystem": subsystem,
            "event_id": event_id,
            "message": message,
        })


# ---------------------------------------------------------------------------
# message.*
# ---------------------------------------------------------------------------

class Message(_Namespace):
    def privmsg(self, target: str, message: str) -> Any:
        return self._q("message.privmsg", {"nick": target, "message": message})

    def notice(self, target: str, message: str) -> Any:
        return self._q("message.notice", {"nick": target, "message": message})

    def numeric(self, nick: str, numeric: int, message: str) -> Any:
        return self._q("message.numeric", {"nick": nick, "numeric": numeric, "message": message})

    def standard_reply(
        self,
        nick: str,
        type_: str,
        code: str,
        description: str,
        context: Optional[str] = None,
    ) -> Any:
        """
        Send an IRCv3 standard reply.

        Args:
            type_:  "FAIL", "WARN", or "NOTE"
        """
        params: dict = {
            "nick": nick,
            "type": type_,
            "code": code,
            "description": description,
        }
        if context is not None:
            params["context"] = context
        return self._q("message.standardreply", params)
