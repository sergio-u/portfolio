# Hermes web surfaces as systemd user services + Tailscale

Covers the built-in dashboard and nesquena/hermes-webui. Copy PATH/HERMES_HOME/ExecStart binary from `systemctl --user cat hermes-gateway.service` (linger already enabled).

## Dashboard (hermes dashboard)
~/.config/systemd/user/hermes-dashboard.service:
  ExecStart="<hermes bin>" "dashboard" "--host" "127.0.0.1" "--port" "9119" "--no-open"
  WorkingDirectory=~/.hermes, Environment=PATH=... HERMES_HOME=..., Restart=always
  [Install] WantedBy=default.target
`systemctl --user daemon-reload && systemctl --user enable --now hermes-dashboard`; verify journal shows `HERMES_DASHBOARD_READY` and `curl 127.0.0.1:9119` -> 200.

Behind Tailscale Serve the loopback dashboard returns 400 "Invalid Host header" (DNS-rebinding guard). Fix, in order:
1. Basic-auth creds in .env: HERMES_DASHBOARD_BASIC_AUTH_USERNAME, _PASSWORD_HASH (scrypt via `plugins.dashboard_auth.basic.hash_password`), _SECRET (random, keeps sessions across restarts). A non-loopback public_url without an auth provider fails closed at startup.
2. `hermes config set dashboard.public_url https://<host>.ts.net:<port>` (exact origin incl. port).
3. Restart, then verify over the ts.net URL: / -> 302 /login; /api/config -> 401; POST /auth/password-login `{provider:"basic",username,password}` -> 200 and /api/config with cookie -> 200; wrong password -> 401. /api/status is intentionally public (version + gateway state).

## hermes-webui (nesquena/hermes-webui)
- Read the repo's docs/onboarding-agent-checklist.md first (role split: human owns passwords and exposure).
- Clone to ~/hermes-webui. Settings in repo `.env` (gitignored, chmod 600): HERMES_WEBUI_HOST=127.0.0.1, PORT=8787, AGENT_DIR=~/.hermes/hermes-agent, PYTHON=<Hermes managed venv python>, DISABLE_LOCAL_VENV=1, DEFAULT_WORKSPACE, PASSWORD.
- Hermes' managed venv is under ~/.hermes/installs/<id>/environments/<id>/venv (find it via `httpx.__file__` after `import hermes_bootstrap`). It has run_agent deps + ruamel.yaml + cryptography, which is enough; no separate venv needed.
- Pitfall: `hermes update` can replace that environment dir, leaving HERMES_WEBUI_PYTHON pointing at a deleted path; webui then crash-loops (`start.sh: ... venv/bin/python: No such file`). Fix: point it at the env the running gateway uses (`grep -o 'environments/[0-9a-f]*' /proc/$(systemctl --user show -p MainPID --value hermes-gateway)/maps | sort -u`), restart, curl /health. Durable fix (pending approval): stop hard-coding the env path. Check webui health after every Hermes update.
- Unit (from docs/supervisor.md): WorkingDirectory=%h/hermes-webui, Environment=HERMES_HOME=%h/.hermes, ExecStart=/bin/bash %h/hermes-webui/start.sh --foreground, Restart=on-failure.
- Verify: /health ok; POST /api/auth/login `{password}` -> 200; /api/onboarding/status (with cookie) hermes_found+imports_ok true; real turn via POST /api/session/new then /api/chat/start `{session_id,message}`, then GET /api/session?session_id=.
- Onboarding reports provider_ready=false for Copilot sourced from gh_cli (it only checks auth.json token fields); chat still works. Don't chase it.

## Exposure (Sergio's pattern)
- Tailscale Serve, tailnet-only, one HTTPS port per service at root: dashboard 8443 -> 9119, webui 9443 -> 8787. `tailscale serve --bg --https=<port> http://127.0.0.1:<local>`.
- Needs root unless `sudo tailscale set --operator=sergio` was run; give Sergio the sudo command, don't attempt sudo. After he says done, re-check `tailscale serve status` — a one-off sudo does not grant operator.
- Confirm `tailscale funnel status` shows nothing public.
- Access: HTTPS works only via the MagicDNS name (cert covers the name; bare IP fails TLS, `http://` gets "Client sent an HTTP request to an HTTPS server"). Sergio's Mac MagicDNS is flaky and he prefers IPs: recommend a client /etc/hosts entry mapping the ts.net name to the tailnet IP (`tailscale ip -4`) over adding plain-HTTP serve routes, which also need dashboard host-allowlisting and break secure cookies.
- Credentials live in ~/.hermes/dashboard-password.txt (user sergio) and ~/.hermes/webui-password.txt (password only); read them when asked.
