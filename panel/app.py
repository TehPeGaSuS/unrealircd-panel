"""
UnrealIRCd Admin Panel — app.py
"""

import os, sys, json, threading, time, logging, hashlib, secrets
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Flask, render_template, redirect, url_for, request,
    session, jsonify, Response, stream_with_context, send_from_directory,
)

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s")
log = logging.getLogger("panel")

app = Flask(__name__)
app.secret_key = os.environ.get("PANEL_SECRET", "change-me-in-production")
app.permanent_session_lifetime = 86400 * 7

# In-memory last-login tracker for the env admin (not persisted to disk)
_env_admin_last_login = {}

RPC_CONFIG = {
    "host":         os.environ.get("RPC_HOST", "127.0.0.1"),
    "port":         int(os.environ.get("RPC_PORT", 8600)),
    "rpc_user":     os.environ.get("RPC_USER", "webpanel"),
    "rpc_password": os.environ.get("RPC_PASSWORD", ""),
    "tls_verify":   os.environ.get("RPC_TLS_VERIFY", "true").lower() == "true",
    "timeout":      10,
}
PANEL_USER       = os.environ.get("PANEL_USER", "admin")
PANEL_PASSWORD   = os.environ.get("PANEL_PASSWORD", "")
NETWORK_NAME     = os.environ.get("NETWORK_NAME", "UnrealIRCd")
USERS_FILE       = Path(__file__).parent / "users.json"
RPC_SERVERS_FILE = Path(__file__).parent / "rpc_servers.json"

# ---------------------------------------------------------------------------
# Permissions
# All available permission keys and their human-readable labels.
# ---------------------------------------------------------------------------
ALL_PERMISSIONS = {
    # IRC users
    "view_users":    "View Users",
    "edit_user":     "Edit Users (nick/vhost/mode/message)",
    "ban_users":     "Ban/Kill Users (G-Line, kill)",
    # Channels
    "view_channels": "View Channels",
    "edit_channel":  "Edit Channels (topic/mode/kick)",
    # Servers
    "view_servers":  "View Servers",
    "rehash":        "Rehash Servers",
    # Bans
    "view_bans":     "View Bans",
    "ban_add":       "Add Bans",
    "ban_del":       "Remove Bans",
    # Logs
    "view_logs":     "View Logs",
    # Panel admin
    "manage_users":  "Manage Panel Users",
}

# Permissions granted to the built-in admin (env user) and role=admin users
ADMIN_PERMS = set(ALL_PERMISSIONS.keys())

# ---------------------------------------------------------------------------
# Panel user helpers
# ---------------------------------------------------------------------------
def _load_extra_users():
    try:
        return json.loads(USERS_FILE.read_text()) if USERS_FILE.exists() else []
    except Exception:
        return []

def _save_extra_users(users):
    USERS_FILE.write_text(json.dumps(users, indent=2))

def _hash_pw(pw):
    salt = secrets.token_hex(16)
    return f"{salt}:{hashlib.sha256((salt+pw).encode()).hexdigest()}"

def _check_pw(pw, stored):
    if ":" not in stored:
        return stored == pw
    salt, h = stored.split(":", 1)
    return hashlib.sha256((salt+pw).encode()).hexdigest() == h

def check_credentials(u, p):
    """Return (role, permissions_set) or None."""
    if u == PANEL_USER and p == PANEL_PASSWORD and PANEL_PASSWORD:
        return "admin", ADMIN_PERMS
    for eu in _load_extra_users():
        if eu["username"] == u and _check_pw(p, eu["password"]):
            role = eu.get("role", "admin")
            if role == "admin":
                return role, ADMIN_PERMS
            perms = set(eu.get("permissions", []))
            return role, perms
    return None, set()

def current_user_can(perm):
    """Check if the logged-in user has a given permission."""
    if session.get("role") == "admin":
        return True
    return perm in session.get("permissions", [])

# ---------------------------------------------------------------------------
# RPC manager
# ---------------------------------------------------------------------------
_rpc = None
_rpc_lock = threading.Lock()

def get_rpc():
    global _rpc
    if _rpc is not None:
        return _rpc
    with _rpc_lock:
        if _rpc is not None:
            return _rpc
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from unrealircd_rpc import Manager
            _rpc = Manager.from_config(RPC_CONFIG, issuer="webpanel")
            log.info("RPC connected to %s:%s", RPC_CONFIG["host"], RPC_CONFIG["port"])
        except Exception as exc:
            log.warning("RPC not available: %s", exc)
    return _rpc

def rpc_call(fn):
    mgr = get_rpc()
    if mgr is None:
        return None, "Not connected to UnrealIRCd"
    try:
        return mgr.with_retry(fn), None
    except Exception as exc:
        log.warning("RPC call failed: %s", exc)
        return None, str(exc)

# ---------------------------------------------------------------------------
# Auth decorators
# ---------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated

def permission_required(perm):
    """Decorator: requires login + specific permission."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get("logged_in"):
                return redirect(url_for("login", next=request.path))
            if not current_user_can(perm):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Permission denied"}), 403
                return render_template("403.html"), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

@app.before_request
def set_rpc_issuer():
    """Keep the RPC issuer in sync with the logged-in panel user.
    Only sends set_issuer when the username has actually changed
    (e.g. after reconnect, or first request after login).
    Uses no_wait so it never blocks the request."""
    if not session.get("logged_in"):
        return
    mgr = get_rpc()
    if mgr is None:
        return
    username = session.get("username", "webpanel")
    # Track the last issuer we sent; resend if it changed or connection was reset
    try:
        client = mgr.get_active()
        if getattr(client, "_last_issuer", None) != username:
            mgr.with_retry(lambda c: c.rpc().set_issuer(username))
            client._last_issuer = username
    except Exception:
        pass


@app.context_processor
def inject_globals():
    perms = set(session.get("permissions", []))
    if session.get("role") == "admin":
        perms = ADMIN_PERMS
    return {
        "network_name":   NETWORK_NAME,
        "current_user":   session.get("username"),
        "current_role":   session.get("role"),
        "user_perms":     perms,
        "can":            current_user_can,
        "env_admin_user": PANEL_USER,
    }

# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@app.route("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "favicon.ico",
                               mimetype="image/x-icon")

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        u, p = request.form.get("username",""), request.form.get("password","")
        role, perms = check_credentials(u, p)
        if role:
            # Record last login timestamp
            _now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if u == PANEL_USER:
                _env_admin_last_login[u] = _now
            else:
                _extra = _load_extra_users()
                for _eu in _extra:
                    if _eu["username"] == u:
                        _eu["last_login"] = _now
                        break
                _save_extra_users(_extra)
            session.clear()
            session.update(
                logged_in=True, username=u, role=role,
                permissions=list(perms)
            )
            session.permanent = True
            mgr = get_rpc()
            if mgr:
                try: mgr.with_retry(lambda c: c.rpc().set_issuer(u))
                except Exception: pass
            return redirect(request.args.get("next") or url_for("dashboard"))
        error = "Invalid credentials"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html", page="dashboard")

@app.route("/users")
@permission_required("view_users")
def users():
    return render_template("users.html", page="users")

@app.route("/channels")
@permission_required("view_channels")
def channels():
    return render_template("channels.html", page="channels")

@app.route("/servers")
@permission_required("view_servers")
def servers():
    return render_template("servers.html", page="servers")

@app.route("/bans")
@permission_required("view_bans")
def bans():
    return render_template("bans.html", page="bans")

@app.route("/spamfilter")
@permission_required("view_bans")
def spamfilter():
    return render_template("spamfilter.html", page="spamfilter")

@app.route("/elines")
@permission_required("view_bans")
def elines():
    return render_template("elines.html", page="elines")

@app.route("/map")
@permission_required("view_users")
def usermap():
    return render_template("map.html", page="map")

@app.route("/logs")
@permission_required("view_logs")
def logs_page():
    return render_template("logs.html", page="logs")

@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html", page="settings")

# ---------------------------------------------------------------------------
# API: Stats
# ---------------------------------------------------------------------------
@app.route("/api/stats")
@login_required
def api_stats():
    result, err = rpc_call(lambda c: c.stats().get(1))
    if err: return jsonify({"error": err}), 503
    from unrealircd_rpc.namespaces import Stats
    return jsonify(Stats(None).parse(result))

# ---------------------------------------------------------------------------
# API: Users
# ---------------------------------------------------------------------------
@app.route("/api/users")
@permission_required("view_users")
def api_users():
    result, err = rpc_call(lambda c: c.user().get_all(2))
    if err: return jsonify({"error": err}), 503
    return jsonify(result or [])

@app.route("/api/users/geo")
@permission_required("view_users")
def api_users_geo():
    """Returns per-country user counts + list of nicks for the map tooltip."""
    result, err = rpc_call(lambda c: c.user().get_all(2))
    if err: return jsonify({"error": err}), 503
    users = result or []

    counts = {}   # country_code -> {count, nicks, country_name}
    local  = 0

    for u in users:
        ip   = u.get("ip", "") if isinstance(u, dict) else getattr(u, "ip", "")
        nick = u.get("name","?") if isinstance(u, dict) else getattr(u, "name","?")
        geo  = u.get("geoip", {}) if isinstance(u, dict) else getattr(u, "geoip", {}) or {}
        if isinstance(geo, dict):
            cc   = geo.get("country_code","")
            name = geo.get("country_name","")
        else:
            cc   = getattr(geo, "country_code", "")
            name = getattr(geo, "country_name", "")

        # Check for local/private IPs
        import re
        is_local = bool(
            not ip or ip in ("::1","localhost") or
            re.match(r"^127\.", ip) or re.match(r"^10\.", ip) or
            re.match(r"^192\.168\.", ip) or
            re.match(r"^172\.(1[6-9]|2\d|3[01])\.", ip) or
            re.match(r"^fc|^fd", ip, re.I)
        )
        if is_local:
            local += 1
            continue

        if not cc:
            cc = "??"
            name = "Unknown"

        if cc not in counts:
            counts[cc] = {"count": 0, "nicks": [], "country_name": name}
        counts[cc]["count"] += 1
        if len(counts[cc]["nicks"]) < 10:   # cap tooltip list
            counts[cc]["nicks"].append(nick)

    return jsonify({"countries": counts, "local": local, "total": len(users)})


@app.route("/api/users/<nick>/detail")
@permission_required("view_users")
def api_user_detail(nick):
    # Level 5 fetches idle time, snomask and flood counters via Remote RPC
    # (requires UnrealIRCd 6.2.6+ on the target server, falls back safely)
    result, err = rpc_call(lambda c: c.user().get(nick, 5))
    if err: return jsonify({"error": err}), 503
    if result is None: return jsonify({"error": "User not found"}), 404
    return jsonify(result)

@app.route("/api/users/<nick>/kill", methods=["POST"])
@permission_required("ban_users")
def api_kill_user(nick):
    d = request.get_json() or {}
    result, err = rpc_call(lambda c: c.user().kill(nick, d.get("reason","No reason")))
    if err: return jsonify({"error": err}), 503
    return jsonify({"ok": True})

@app.route("/api/users/<nick>/nick", methods=["POST"])
@permission_required("edit_user")
def api_set_nick(nick):
    d = request.get_json() or {}
    result, err = rpc_call(lambda c: c.user().set_nick(nick, d.get("newnick","")))
    if err: return jsonify({"error": err}), 503
    return jsonify({"ok": True})

@app.route("/api/users/<nick>/vhost", methods=["POST"])
@permission_required("edit_user")
def api_set_vhost(nick):
    d = request.get_json() or {}
    result, err = rpc_call(lambda c: c.user().set_vhost(nick, d.get("vhost","")))
    if err: return jsonify({"error": err}), 503
    return jsonify({"ok": True})

@app.route("/api/users/<nick>/mode", methods=["POST"])
@permission_required("edit_user")
def api_set_user_mode(nick):
    d = request.get_json() or {}
    result, err = rpc_call(lambda c: c.user().set_mode(nick, d.get("modes","")))
    if err: return jsonify({"error": err}), 503
    return jsonify({"ok": True})

@app.route("/api/users/<nick>/message", methods=["POST"])
@permission_required("edit_user")
def api_message_user(nick):
    d = request.get_json() or {}
    msg, type_ = d.get("message",""), d.get("type","privmsg")
    fn = (lambda c: c.message().notice(nick, msg)) if type_=="notice" \
         else (lambda c: c.message().privmsg(nick, msg))
    result, err = rpc_call(fn)
    if err: return jsonify({"error": err}), 503
    return jsonify({"ok": True})

@app.route("/api/whowas")
@permission_required("view_users")
def api_whowas():
    nick = request.args.get("nick")
    ip   = request.args.get("ip")
    params = {}
    if nick: params["nick"] = nick
    if ip:   params["ip"]   = ip
    result, err = rpc_call(lambda c: c.query("whowas.get", params or None))
    if err: return jsonify({"error": err}), 503
    return jsonify(result.get("list", []) if isinstance(result, dict) else [])

# ---------------------------------------------------------------------------
# API: Channels
# ---------------------------------------------------------------------------
@app.route("/api/channels")
@permission_required("view_channels")
def api_channels():
    result, err = rpc_call(lambda c: c.channel().get_all(1))
    if err: return jsonify({"error": err}), 503
    return jsonify(result or [])

@app.route("/api/channels/<path:name>/detail")
@permission_required("view_channels")
def api_channel_detail(name):
    chan = "#"+name if not name.startswith("#") else name
    result, err = rpc_call(lambda c: c.channel().get(chan, 4))
    if err: return jsonify({"error": err}), 503
    if result is None: return jsonify({"error": "Channel not found"}), 404
    return jsonify(result)

@app.route("/api/channels/<path:name>/topic", methods=["POST"])
@permission_required("edit_channel")
def api_set_topic(name):
    d = request.get_json() or {}
    chan = "#"+name if not name.startswith("#") else name
    result, err = rpc_call(lambda c: c.channel().set_topic(chan, d.get("topic","")))
    if err: return jsonify({"error": err}), 503
    return jsonify({"ok": True})

@app.route("/api/channels/<path:name>/mode", methods=["POST"])
@permission_required("edit_channel")
def api_set_channel_mode(name):
    d = request.get_json() or {}
    chan = "#"+name if not name.startswith("#") else name
    result, err = rpc_call(lambda c: c.channel().set_mode(chan, d.get("modes",""), d.get("parameters","")))
    if err: return jsonify({"error": err}), 503
    return jsonify({"ok": True})

@app.route("/api/channels/<path:name>/kick", methods=["POST"])
@permission_required("edit_channel")
def api_kick_from_channel(name):
    d = request.get_json() or {}
    chan = "#"+name if not name.startswith("#") else name
    result, err = rpc_call(lambda c: c.channel().kick(chan, d.get("nick",""), d.get("reason","No reason")))
    if err: return jsonify({"error": err}), 503
    return jsonify({"ok": True})

# ---------------------------------------------------------------------------
# API: Servers
# ---------------------------------------------------------------------------
@app.route("/api/servers")
@permission_required("view_servers")
def api_servers():
    # get_all() returns linked/remote servers only; get() returns the local server
    result, err = rpc_call(lambda c: c.server().get_all())
    if err: return jsonify({"error": err}), 503
    servers = list(result or [])
    local, err2 = rpc_call(lambda c: c.server().get(object_detail_level=3))
    if not err2 and local:
        # Avoid duplicates (some configs may include local in list)
        local_name = local.get("name") if isinstance(local, dict) else getattr(local, "name", None)
        if not any((s.get("name") if isinstance(s, dict) else getattr(s, "name", None)) == local_name for s in servers):
            servers.insert(0, local)
    return jsonify(servers)

@app.route("/api/servers/<srvname>/rehash", methods=["POST"])
@permission_required("rehash")
def api_rehash(srvname):
    result, err = rpc_call(lambda c: c.server().rehash(srvname))
    if err: return jsonify({"error": err}), 503
    return jsonify({"ok": True})

# ---------------------------------------------------------------------------
# API: Bans
# ---------------------------------------------------------------------------
@app.route("/api/bans")
@permission_required("view_bans")
def api_bans():
    result, err = rpc_call(lambda c: c.server_ban().get_all())
    if err: return jsonify({"error": err}), 503
    return jsonify(result or [])

@app.route("/api/bans", methods=["POST"])
@permission_required("ban_add")
def api_add_ban():
    d = request.get_json() or {}
    result, err = rpc_call(lambda c: c.server_ban().add(
        d.get("name",""), d.get("type","gline"), d.get("duration","1d"), d.get("reason","")))
    if err: return jsonify({"error": err}), 503
    return jsonify({"ok": True})

@app.route("/api/bans/<path:name>", methods=["DELETE"])
@permission_required("ban_del")
def api_del_ban(name):
    result, err = rpc_call(lambda c: c.server_ban().delete(name, request.args.get("type","gline")))
    if err: return jsonify({"error": err}), 503
    return jsonify({"ok": True})

@app.route("/api/bans/batch-delete", methods=["POST"])
@permission_required("ban_del")
def api_bans_batch_delete():
    d = request.get_json() or {}
    items = d.get("items", [])  # [{name, type}, ...]
    errors = []
    for item in items:
        _, err = rpc_call(lambda c, i=item: c.server_ban().delete(i["name"], i["type"]))
        if err:
            errors.append(f"{item['name']}: {err}")
    if errors:
        return jsonify({"error": "; ".join(errors)}), 207
    return jsonify({"ok": True})

# ---------------------------------------------------------------------------
# API: Spamfilter
# ---------------------------------------------------------------------------
@app.route("/api/spamfilter")
@permission_required("view_bans")
def api_spamfilter_list():
    result, err = rpc_call(lambda c: c.spamfilter().get_all())
    if err: return jsonify({"error": err}), 503
    return jsonify(result or [])

@app.route("/api/spamfilter", methods=["POST"])
@permission_required("ban_add")
def api_spamfilter_add():
    d = request.get_json() or {}
    result, err = rpc_call(lambda c: c.spamfilter().add(
        d.get("name", ""),
        d.get("match_type", "simple"),
        d.get("spamfilter_targets", "p"),
        d.get("ban_action", "block"),
        d.get("ban_duration", "0"),
        d.get("reason", ""),
    ))
    if err: return jsonify({"error": err}), 503
    return jsonify({"ok": True})

@app.route("/api/spamfilter", methods=["DELETE"])
@permission_required("ban_del")
def api_spamfilter_delete():
    d = request.get_json() or {}
    result, err = rpc_call(lambda c: c.spamfilter().delete(
        d.get("name", ""),
        d.get("match_type", "simple"),
        d.get("spamfilter_targets", "p"),
        d.get("ban_action", "block"),
    ))
    if err: return jsonify({"error": err}), 503
    return jsonify({"ok": True})

# ---------------------------------------------------------------------------
# API: E-Lines (ban exceptions)
# ---------------------------------------------------------------------------
@app.route("/api/elines")
@permission_required("view_bans")
def api_elines_list():
    result, err = rpc_call(lambda c: c.server_ban_exception().get_all())
    if err: return jsonify({"error": err}), 503
    return jsonify(result or [])

@app.route("/api/elines", methods=["POST"])
@permission_required("ban_add")
def api_elines_add():
    d = request.get_json() or {}
    result, err = rpc_call(lambda c: c.server_ban_exception().add(
        d.get("name", ""),
        d.get("exception_types", "kGzZs"),
        d.get("reason", ""),
        duration=d.get("duration") or None,
    ))
    if err: return jsonify({"error": err}), 503
    return jsonify({"ok": True})

@app.route("/api/elines/<path:name>", methods=["DELETE"])
@permission_required("ban_del")
def api_elines_delete(name):
    result, err = rpc_call(lambda c: c.server_ban_exception().delete(name))
    if err: return jsonify({"error": err}), 503
    return jsonify({"ok": True})


@app.route("/api/logs/stream")
@permission_required("view_logs")
def api_log_stream():
    def generate():
        mgr = get_rpc()
        if mgr is None:
            yield 'event: error\ndata: {"error":"RPC not connected"}\n\n'; return
        try:
            sc = mgr.new_dedicated_client()
        except Exception as exc:
            yield f'event: error\ndata: {{"error":"{exc}"}}\n\n'; return
        try:
            sc.log().subscribe(["all","!debug"])
        except Exception as exc:
            sc.close()
            yield f'event: error\ndata: {{"error":"{exc}"}}\n\n'; return
        yield 'event: connected\ndata: {"status":"connected"}\n\n'
        last_ka = time.time()
        try:
            while True:
                event = sc.event_loop_recv(timeout=2.0)
                if time.time()-last_ka > 15:
                    yield ": keepalive\n\n"; last_ka = time.time()
                if not event or not isinstance(event, dict): continue
                if "msg" not in event and "message" not in event: continue
                yield f"event: log\ndata: {json.dumps(event)}\n\n"
        except Exception as exc:
            log.warning("Log stream error: %s", exc)
        finally:
            try: sc.close()
            except Exception: pass

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@app.route("/api/logs")
@permission_required("view_logs")
def api_logs():
    result, err = rpc_call(lambda c: c.log().get_all())
    if err: return jsonify({"error": err}), 503
    return jsonify(result or [])

# ---------------------------------------------------------------------------
# API: Change own password
# ---------------------------------------------------------------------------
@app.route("/api/account/password", methods=["POST"])
@login_required
def api_change_password():
    d = request.get_json() or {}
    current  = d.get("current", "")
    new_pw   = d.get("new", "")
    username = session.get("username")

    if not new_pw or len(new_pw) < 8:
        return jsonify({"error": "New password must be at least 8 characters"}), 400

    # Env admin: verify against PANEL_PASSWORD, cannot change via UI
    if username == PANEL_USER:
        return jsonify({"error": "The primary admin password is set via the .env file"}), 403

    users = _load_extra_users()
    user = next((u for u in users if u["username"] == username), None)
    if not user:
        return jsonify({"error": "User not found"}), 404

    if not _check_pw(current, user["password"]):
        return jsonify({"error": "Current password is incorrect"}), 403

    user["password"] = _hash_pw(new_pw)
    _save_extra_users(users)
    return jsonify({"ok": True})

# ---------------------------------------------------------------------------
# API: Settings — current user info + permissions
# ---------------------------------------------------------------------------
@app.route("/api/account")
@login_required
def api_account():
    return jsonify({
        "username":    session.get("username"),
        "role":        session.get("role"),
        "permissions": session.get("permissions", []),
        "is_env_admin": session.get("username") == PANEL_USER,
    })

# ---------------------------------------------------------------------------
# API: Settings — Panel users (manage_users permission required)
# ---------------------------------------------------------------------------
@app.route("/api/settings/users")
@permission_required("manage_users")
def api_settings_users_list():
    users = [{
        "username":   PANEL_USER,
        "role":       "admin",
        "permissions": list(ADMIN_PERMS),
        "last_login": _env_admin_last_login.get(PANEL_USER),
    }]
    for u in _load_extra_users():
        users.append({
            "username":    u["username"],
            "role":        u.get("role", "admin"),
            "permissions": u.get("permissions", []),
            "last_login":  u.get("last_login"),
        })
    return jsonify(users)

@app.route("/api/settings/users", methods=["POST"])
@permission_required("manage_users")
def api_settings_users_add():
    d = request.get_json() or {}
    username    = d.get("username","").strip()
    password    = d.get("password","")
    role        = d.get("role","viewer")
    permissions = d.get("permissions", [])

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if username == PANEL_USER:
        return jsonify({"error": "Cannot shadow the env admin"}), 400

    users = _load_extra_users()
    if any(u["username"]==username for u in users):
        return jsonify({"error": "User already exists"}), 409

    # Validate permissions
    valid_perms = [p for p in permissions if p in ALL_PERMISSIONS]
    users.append({
        "username":    username,
        "password":    _hash_pw(password),
        "role":        role,
        "permissions": valid_perms if role != "admin" else [],
    })
    _save_extra_users(users)
    return jsonify({"ok": True})

@app.route("/api/settings/users/<username>", methods=["PUT"])
@permission_required("manage_users")
def api_settings_users_update(username):
    if username == PANEL_USER:
        return jsonify({"error": "Cannot modify env admin"}), 403
    d = request.get_json() or {}
    users = _load_extra_users()
    user = next((u for u in users if u["username"]==username), None)
    if not user:
        return jsonify({"error": "User not found"}), 404

    if "role" in d:
        user["role"] = d["role"]
    if "permissions" in d:
        user["permissions"] = [p for p in d["permissions"] if p in ALL_PERMISSIONS]
    if "password" in d and d["password"]:
        if len(d["password"]) < 8:
            return jsonify({"error": "Password must be at least 8 characters"}), 400
        user["password"] = _hash_pw(d["password"])

    _save_extra_users(users)
    return jsonify({"ok": True})

@app.route("/api/settings/users/<username>", methods=["DELETE"])
@permission_required("manage_users")
def api_settings_users_delete(username):
    if username == PANEL_USER:
        return jsonify({"error": "Cannot delete env admin"}), 403
    _save_extra_users([u for u in _load_extra_users() if u["username"]!=username])
    return jsonify({"ok": True})

# ---------------------------------------------------------------------------
# API: Settings — available permissions list
# ---------------------------------------------------------------------------
@app.route("/api/settings/permissions")
@permission_required("manage_users")
def api_settings_permissions():
    return jsonify(ALL_PERMISSIONS)

# ---------------------------------------------------------------------------
# API: Settings — RPC servers
# ---------------------------------------------------------------------------
def _load_rpc_servers():
    try:
        return json.loads(RPC_SERVERS_FILE.read_text()) if RPC_SERVERS_FILE.exists() else []
    except Exception:
        return []

def _save_rpc_servers(servers):
    RPC_SERVERS_FILE.write_text(json.dumps(servers, indent=2))

@app.route("/api/settings/rpc-servers")
@login_required
def api_settings_rpc_list():
    mgr = get_rpc()
    active = mgr._active if mgr else None
    out = [{"name":"Primary (env)","host":RPC_CONFIG["host"],"port":RPC_CONFIG["port"],
            "active": active in (None,"default")}]
    out += [{"name":s["name"],"host":s["host"],"port":s["port"],
             "active":active==s["name"]} for s in _load_rpc_servers()]
    return jsonify(out)

@app.route("/api/settings/rpc-servers/test", methods=["POST"])
@login_required
def api_settings_rpc_test():
    d = request.get_json() or {}
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from unrealircd_rpc import Manager
        Manager.test_connection(d)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503

@app.route("/api/settings/rpc-servers", methods=["POST"])
@permission_required("manage_users")
def api_settings_rpc_add():
    d = request.get_json() or {}
    name = d.get("name","").strip()
    if not name: return jsonify({"error":"name required"}), 400
    servers = _load_rpc_servers()
    if any(s["name"]==name for s in servers):
        return jsonify({"error":"Server name already exists"}), 409
    servers.append({"name":name, "host":d.get("host","127.0.0.1"),
        "port":int(d.get("port",8600)), "rpc_user":d.get("rpc_user","webpanel"),
        "rpc_password":d.get("rpc_password",""), "tls_verify":bool(d.get("tls_verify",False))})
    _save_rpc_servers(servers)
    return jsonify({"ok": True})

@app.route("/api/settings/rpc-servers/<srvname>", methods=["DELETE"])
@permission_required("manage_users")
def api_settings_rpc_delete(srvname):
    _save_rpc_servers([s for s in _load_rpc_servers() if s["name"]!=srvname])
    return jsonify({"ok": True})

@app.route("/api/settings/rpc-servers/<srvname>/activate", methods=["POST"])
@login_required
def api_settings_rpc_activate(srvname):
    global _rpc
    srv = next((s for s in _load_rpc_servers() if s["name"]==srvname), None)
    if not srv: return jsonify({"error":"Server not found"}), 404
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from unrealircd_rpc import Manager
        with _rpc_lock:
            _rpc = Manager.from_config({**srv,"name":srvname},
                issuer=session.get("username","webpanel"))
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not PANEL_PASSWORD:
        print("ERROR: Set PANEL_PASSWORD in .env", file=sys.stderr); sys.exit(1)
    app.run(host="0.0.0.0", port=5000, debug=False)
