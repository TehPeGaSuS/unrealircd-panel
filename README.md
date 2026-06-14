# UnrealIRCd Admin Panel

Web-based admin panel for UnrealIRCd, built on the JSON-RPC interface.
Flask backend, no frontend build step — drop in and run.

## Features

- Live network stats (users, channels, servers, opers, bans)
- User management: kill, set vhost
- Channel management: list, set topic
- Server management: list, rehash
- Ban management: add/remove G-Lines, K-Lines, Z-Lines, etc.
- Live log streaming via SSE (Server-Sent Events)
- Responsive — works on desktop and mobile
- Light/dark theme toggle, preference stored in browser

---

## Directory layout

```
unrealircd-panel/
├── .env                    ← your config (copy from .env.example)
├── .env.example            ← config template
├── requirements.txt        ← pip dependencies
├── unrealircd-panel.service     ← systemd user unit
│
├── unrealircd_rpc/         ← RPC client library
│   ├── __init__.py
│   ├── connection.py       ← WebSocket JSON-RPC transport
│   ├── manager.py          ← connection manager + retry logic
│   ├── namespaces.py       ← RPC method wrappers
│   └── audit.py            ← audit log helpers
│
└── panel/                  ← Flask application
    ├── app.py              ← routes + API endpoints
    ├── static/
    │   ├── css/panel.css
    │   └── js/panel.js
    └── templates/
        ├── base.html
        ├── login.html
        ├── dashboard.html
        ├── users.html
        ├── channels.html
        ├── servers.html
        ├── bans.html
        └── logs.html
```

---

## Setup

### 1. Install dependencies

```bash
cd ~/unrealircd-panel
pip install -r requirements.txt --break-system-packages
```

### 2. Configure

```bash
cp .env.example .env
nano .env   # fill in RPC_PASSWORD, PANEL_PASSWORD, PANEL_SECRET, etc.
```

The only values that matter out of the box:

| Variable | What to set |
|---|---|
| `RPC_PASSWORD` | Matches `password` in your `rpc-user` block |
| `PANEL_PASSWORD` | Your panel login password |
| `PANEL_SECRET` | Any long random string (`python3 -c "import secrets; print(secrets.token_hex(32))"`) |
| `NETWORK_NAME` | Displayed in the UI (default: `UnrealIRCd`) |
| `RPC_TLS_VERIFY` | `false` for self-signed certs, `true` for real certs |

### 3. UnrealIRCd config

Add to `unrealircd.conf` (or an included file):

```
include "rpc.modules.default.conf";

rpc-user webpanel {
    match { ip 127.0.0.1; }
    password "your_rpc_password_here";
    rpc-class "full";
}

listen {
    ip 127.0.0.1;
    port 8600;
    options { rpc; tls; }
}
```

Then rehash or restart UnrealIRCd.

### 4. Run (dev)

```bash
cd ~/unrealircd-panel/panel
source ../.env  # or: set -a; source ../.env; set +a
python app.py
```

### 5. Run (production — systemd)

```bash
# Install the unit
cp ~/unrealircd-panel/unrealircd-panel.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now unrealircd-panel

# Check status
systemctl --user status unrealircd-panel
journalctl --user -u unrealircd-panel -f
```

The panel listens on `127.0.0.1:5000`.

---

## Cloudflare Zero Trust tunnel

Point a CF tunnel ingress rule at `http://127.0.0.1:5000`.

**Important:** enable "Match SNI to Host" on the tunnel ingress rule,
otherwise Apache/nginx cert matching will fail if you have other vhosts.

---

## Production notes

- `gunicorn -w 1 --threads 4` is intentional. The RPC Manager is
  module-level state; single worker keeps one persistent WS connection
  to UnrealIRCd while threads handle concurrent HTTP requests.
- Log streaming (`/logs`) opens a second dedicated WS connection to
  UnrealIRCd for the SSE stream — this is correct by design and avoids
  multiplexing conflicts.
- The `.env` file is read by the systemd unit via `EnvironmentFile=`.
  It is **not** auto-loaded in dev — either `source` it or export vars.

---

## Extending

The `unrealircd_rpc` library covers the full RPC surface:
`user`, `channel`, `server`, `server_ban`, `server_ban_exception`,
`name_ban`, `spamfilter`, `stats`, `log`, `message`, `rpc`.

Add a new page: create a template, add a `@app.route` + `@login_required`
in `app.py`, add any `/api/...` endpoints needed, link it in `base.html`.
