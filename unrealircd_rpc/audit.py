"""
unrealircd_rpc.audit
~~~~~~~~~~~~~~~~~~~~
Sends webpanel admin actions back through UnrealIRCd's own log system
via the log.send RPC method.

This means logins, bans, kills, etc. appear in UnrealIRCd's logs
alongside IRC events — under the "webpanel" subsystem.

All functions are non-blocking (run in a daemon thread) so they don't
add latency to Flask responses.

Event ID naming convention: WEBPANEL_<ACTION> in SCREAMING_SNAKE_CASE.

Usage:
    from unrealircd_rpc.audit import audit_login, audit_ban

    audit_login(rpc_manager, username="alice", ip="1.2.3.4")
    audit_ban(rpc_manager, by="alice", target="*@badhost.com", type_="gline", reason="spam")
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .manager import Manager

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event ID constants
# ---------------------------------------------------------------------------

EV_LOGIN             = "WEBPANEL_LOGIN"
EV_LOGOUT            = "WEBPANEL_LOGOUT"
EV_BAN_ADD           = "WEBPANEL_BAN_ADD"
EV_BAN_DEL           = "WEBPANEL_BAN_DEL"
EV_NAMEBAN_ADD       = "WEBPANEL_NAMEBAN_ADD"
EV_NAMEBAN_DEL       = "WEBPANEL_NAMEBAN_DEL"
EV_EXCEPTION_ADD     = "WEBPANEL_EXCEPTION_ADD"
EV_EXCEPTION_DEL     = "WEBPANEL_EXCEPTION_DEL"
EV_SPAMFILTER_ADD    = "WEBPANEL_SPAMFILTER_ADD"
EV_SPAMFILTER_DEL    = "WEBPANEL_SPAMFILTER_DEL"
EV_USER_KILL         = "WEBPANEL_USER_KILL"
EV_USER_NICK         = "WEBPANEL_USER_NICK"
EV_USER_VHOST        = "WEBPANEL_USER_VHOST"
EV_USER_MODE         = "WEBPANEL_USER_MODE"
EV_CHANNEL_TOPIC     = "WEBPANEL_CHANNEL_TOPIC"
EV_CHANNEL_MODE      = "WEBPANEL_CHANNEL_MODE"
EV_CHANNEL_KICK      = "WEBPANEL_CHANNEL_KICK"
EV_SERVER_REHASH     = "WEBPANEL_SERVER_REHASH"
EV_PANEL_USER_CREATE = "WEBPANEL_PANEL_USER_CREATE"
EV_PANEL_USER_DELETE = "WEBPANEL_PANEL_USER_DELETE"
EV_PANEL_USER_UPDATE = "WEBPANEL_PANEL_USER_UPDATE"
EV_RPC_SERVER_ADD    = "WEBPANEL_RPC_SERVER_ADD"
EV_RPC_SERVER_DEL    = "WEBPANEL_RPC_SERVER_DEL"

SUBSYSTEM = "webpanel"


# ---------------------------------------------------------------------------
# Core sender
# ---------------------------------------------------------------------------

def _send_async(manager: "Manager", message: str, level: str, event_id: str) -> None:
    """Fire-and-forget log.send in a daemon thread."""
    def _do():
        try:
            manager.with_retry(
                lambda conn: conn.log().send(message, level=level, subsystem=SUBSYSTEM, event_id=event_id)
            )
        except Exception as exc:
            log.warning("audit: failed to send log (%s): %s", event_id, exc)

    t = threading.Thread(target=_do, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Public audit helpers
# ---------------------------------------------------------------------------

def audit_login(manager: "Manager", username: str, ip: str) -> None:
    _send_async(manager, f"Panel user '{username}' logged in from {ip}", "info", EV_LOGIN)


def audit_logout(manager: "Manager", username: str) -> None:
    _send_async(manager, f"Panel user '{username}' logged out", "info", EV_LOGOUT)


def audit_ban_add(
    manager: "Manager",
    by: str,
    target: str,
    type_: str,
    duration: str,
    reason: str,
) -> None:
    msg = f"{by} added {type_.upper()} on '{target}' (duration: {duration}, reason: {reason})"
    _send_async(manager, msg, "info", EV_BAN_ADD)


def audit_ban_del(manager: "Manager", by: str, target: str, type_: str) -> None:
    msg = f"{by} removed {type_.upper()} on '{target}'"
    _send_async(manager, msg, "info", EV_BAN_DEL)


def audit_nameban_add(manager: "Manager", by: str, name: str, reason: str) -> None:
    msg = f"{by} added Q-Line on '{name}' (reason: {reason})"
    _send_async(manager, msg, "info", EV_NAMEBAN_ADD)


def audit_nameban_del(manager: "Manager", by: str, name: str) -> None:
    msg = f"{by} removed Q-Line on '{name}'"
    _send_async(manager, msg, "info", EV_NAMEBAN_DEL)


def audit_spamfilter_add(manager: "Manager", by: str, name: str, action: str) -> None:
    msg = f"{by} added spamfilter '{name}' (action: {action})"
    _send_async(manager, msg, "info", EV_SPAMFILTER_ADD)


def audit_spamfilter_del(manager: "Manager", by: str, name: str) -> None:
    msg = f"{by} removed spamfilter '{name}'"
    _send_async(manager, msg, "info", EV_SPAMFILTER_DEL)


def audit_user_kill(manager: "Manager", by: str, nick: str, reason: str) -> None:
    msg = f"{by} killed '{nick}' (reason: {reason})"
    _send_async(manager, msg, "info", EV_USER_KILL)


def audit_user_nick(manager: "Manager", by: str, old_nick: str, new_nick: str) -> None:
    msg = f"{by} changed nick '{old_nick}' -> '{new_nick}'"
    _send_async(manager, msg, "info", EV_USER_NICK)


def audit_user_vhost(manager: "Manager", by: str, nick: str, vhost: str) -> None:
    msg = f"{by} set vhost on '{nick}' to '{vhost}'"
    _send_async(manager, msg, "info", EV_USER_VHOST)


def audit_user_mode(manager: "Manager", by: str, nick: str, modes: str) -> None:
    msg = f"{by} set mode '{modes}' on '{nick}'"
    _send_async(manager, msg, "info", EV_USER_MODE)


def audit_channel_topic(manager: "Manager", by: str, channel: str, topic: str) -> None:
    msg = f"{by} set topic on {channel}: {topic!r}"
    _send_async(manager, msg, "info", EV_CHANNEL_TOPIC)


def audit_channel_mode(manager: "Manager", by: str, channel: str, modes: str) -> None:
    msg = f"{by} set mode '{modes}' on {channel}"
    _send_async(manager, msg, "info", EV_CHANNEL_MODE)


def audit_channel_kick(manager: "Manager", by: str, channel: str, nick: str, reason: str) -> None:
    msg = f"{by} kicked '{nick}' from {channel} (reason: {reason})"
    _send_async(manager, msg, "info", EV_CHANNEL_KICK)


def audit_server_rehash(manager: "Manager", by: str, server: str) -> None:
    msg = f"{by} rehashed server '{server}'"
    _send_async(manager, msg, "info", EV_SERVER_REHASH)


def audit_panel_user_create(manager: "Manager", by: str, new_user: str) -> None:
    msg = f"Panel account '{new_user}' created by '{by}'"
    _send_async(manager, msg, "info", EV_PANEL_USER_CREATE)


def audit_panel_user_delete(manager: "Manager", by: str, deleted_user: str) -> None:
    msg = f"Panel account '{deleted_user}' deleted by '{by}'"
    _send_async(manager, msg, "info", EV_PANEL_USER_DELETE)


def audit_panel_user_update(manager: "Manager", by: str, updated_user: str) -> None:
    msg = f"Panel account '{updated_user}' updated by '{by}'"
    _send_async(manager, msg, "info", EV_PANEL_USER_UPDATE)


def audit_rpc_server_add(manager: "Manager", by: str, server_name: str) -> None:
    msg = f"RPC server '{server_name}' added by '{by}'"
    _send_async(manager, msg, "info", EV_RPC_SERVER_ADD)


def audit_rpc_server_del(manager: "Manager", by: str, server_name: str) -> None:
    msg = f"RPC server '{server_name}' removed by '{by}'"
    _send_async(manager, msg, "info", EV_RPC_SERVER_DEL)
