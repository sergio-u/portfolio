---
name: hermes-host-admin
description: "Use when administering Sergio's own Hermes install."
version: 1.0.0
---

# Hermes host administration (Sergio's VM)

Covers the memory provider, toolsets, the dashboard and Tailscale exposure. Complements the bundled `hermes-agent` skill (load it too). This carries the procedures that actually worked on this host and Sergio's preferences.

## Always-on rules
- Ask before every config/.env/service write. If an approval prompt times out, do NOT retry; restate the exact command and wait for "go ahead".
- Use `hermes config set` / `hermes tools enable` rather than hand-editing config.yaml. Back up `.env` before editing it and remind Sergio to delete the backup (it holds keys).
- Verify recalled memory against live state. Hindsight auto-recall injects old hypotheses (including wrong ones) as "authoritative"; check the config and logs before repeating them.
- Never echo secrets (passwords, API keys) in chat: auto-retain stores conversation turns in the memory bank. Write them to a 0600 file or have Sergio set them himself.
- This conversation's toolset is frozen at session start. To verify new tools, run a fresh `hermes chat -q '...'` and grep `~/.hermes/logs/*.log`.

## Memory provider: Hindsight (self-hosted)
1. `hermes plugins install hindsight` (it's a catalog plugin now), then `hermes plugins enable hindsight`.
2. Put `HINDSIGHT_API_KEY=...` in `~/.hermes/.env`.
3. Write `$HERMES_HOME/hindsight/config.json` with `mode: cloud`, `api_url`, `bank_id`, and `retain_tags`. Cloud mode accepts a custom api_url, so local_external isn't needed.
4. Create the bank: `PUT {api}/v1/default/banks/<id>` with `{name, mission}` (Bearer auth). List banks with `GET /v1/default/banks`.
5. `hermes config set memory.provider hindsight`, then `hermes memory status`.
6. Verify the tools load with a fresh session that calls hindsight_retain and hindsight_recall. Recall returns synthesized observations, not verbatim text.
- If the tools are missing, grep the logs for `'memory' toolset is gated off`. The cause is a missing `memory` in `platform_toolsets.<platform>` (fix: `hermes tools enable memory [--platform X]`). `memory.memory_enabled` only controls the built-in MEMORY.md store and is not the cause.

## Toolsets
- Per platform. A saved `platform_toolsets.<p>` list is authoritative; platforms without a list get defaults; `agent.disabled_toolsets` removes toolsets everywhere and is applied last.
- `hermes tools enable a b c` (defaults to cli); `--platform telegram` targets Telegram. `hermes tools --summary` needs a TTY, so read config.yaml instead.
- Sergio prefers the CLI and Telegram to have the same toolsets.

## Services inventory and updates
- Three systemd user units in `~/.config/systemd/user/`: `hermes-gateway` (written by `hermes gateway install`), `hermes-dashboard` (hand-written, copied from the gateway unit), `hermes-webui` (hand-written; runs `~/hermes-webui/start.sh --foreground`, port 8787, data in ~/.hermes/webui). These unit files sit outside the ~/.hermes git repo.
- Gateway + dashboard share the agent install, so `hermes update` covers both; WebUI is a separate git clone of nesquena/hermes-webui and needs its own pull.
- Use `~/.local/bin/hermes-update-all` (source copy: `scripts/hermes-update-all` in this skill; reinstall from it if missing) (`--check` is read-only; default = `hermes update --no-gateway-restart` + WebUI `merge --ff-only` + restart all three + health-check :9119 and :8787/health; `--restart` skips updating; `--reset-webui` hard-resets if upstream history was rewritten). Restart WebUI after every agent update too, because it imports agent code.
- Run updates/restarts from a normal shell, not from a chat turn: restarting the gateway kills in-flight Telegram turns. Run only `--check` without explicit approval.
- `hermes update --check` on the stable channel can report "no newer release" when the checkout is ahead of the latest tag; that is not an error.
- The hand-written dashboard unit hard-codes the versioned node/npm tool paths in PATH. Re-check them after an agent update that bumps Node.

## Dashboard as a service + Tailscale
- Run it as a systemd user unit (`~/.config/systemd/user/hermes-dashboard.service`, modeled on hermes-gateway.service) with `ExecStart=... hermes dashboard --host 127.0.0.1 --port 9119 --no-open` and `WantedBy=default.target`. Linger is on.
- Exposure preference: Tailscale Serve, tailnet-only, ONE HTTPS PORT PER SERVICE at root (Sergio's pattern: 8443, 9443...). Avoid subpaths, because SPAs break under them. Check with `tailscale serve status` and `tailscale funnel status`.
- `tailscale serve` needs root unless `sudo tailscale set --operator=$USER` has been run once. Give Sergio the command; don't try sudo.
- Through the proxy, a loopback-bound dashboard returns 400 "Invalid Host header" until `dashboard.public_url` is set to the exact ts.net origin (with port). A non-loopback public_url REQUIRES an auth provider (e.g. HERMES_DASHBOARD_BASIC_AUTH_USERNAME + _PASSWORD_HASH + _SECRET in .env), or startup fails closed (per the Hermes docs).
- Hindsight bank in use is set by `bank_id` in `~/.hermes/hindsight/config.json` (Hindsight says "bank", not "namespace"); read it there rather than trusting recalled memory.
- Other self-hosted services (Hindsight etc.) sit behind Caddy on a container host, with a private DNS zone resolving to tailnet IPs. Resolve with `getent ahosts` to tell tailnet-only from public.
