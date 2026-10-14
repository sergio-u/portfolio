# Agent-to-agent interfaces: Pi, Claude Code, other Hermes <-> Hermes

Use when the user asks how another agent can hand off work to / call Hermes, or how Hermes can call another agent.

## Decision table

| Path | Direction | Lands in | Use when |
|---|---|---|---|
| `hermes chat -Q --query-file note.md` (`--format stream-json`) | caller -> Hermes | new CLI session (resumable via `--resume`) | caller on the SAME machine; zero setup |
| API server (`/v1/runs`, `/v1/responses`, `/api/sessions/*`) on :8642 | caller -> Hermes over HTTP | API session | cross-machine, plain HTTP+bearer, already-running gateway |
| A2A gateway platform (:9900, JSON-RPC `SendMessage`) | bidirectional | live gateway session keyed by `contextId` | cross-machine, standard protocol, per-peer tokens, audit, anti-loop. Preferred default for Pi<->Hermes |
| Webhooks | event -> Hermes run | webhook session | event-triggered, not conversational |
| `hermes mcp serve` | caller READS Hermes messaging conversations | n/a | NOT a task-handoff path: exposes conversations_list/messages_read/attachments_fetch etc., no 'run task' tool |
| ACP | editor -> Hermes | IDE | editors, not agents |

Pi-side packages (from READMEs, source not reviewed):
| Package | Fit |
|---|---|
| `@bacnh85/pi-a2a` | A2A v1.0 peer, Hermes is its primary interop target; inbound tasks run in an ISOLATED child Pi session in `server.workspace`, not the live TUI (progress mirrored as `[A2A inbound]`) |
| `pi-intercom` | Pi<->Pi live sessions, same machine only |
| `agent-comms` | cross-harness live mesh; cross-machine only via a relay hub (public by default; self-host `npx wire-mesh`); Hermes only via generic MCP bridge (drain-on-tool-call, no wake) |
| `pi-fabric` | in-Pi orchestration runtime, not inter-agent messaging |

## Procedure
1. Establish whether caller and Hermes share a machine; cross-machine rules out the CLI path.
2. Check what is already running before proposing setup: `ss -ltnp | grep -E '8642|9900'`, `curl -s http://<host>:8642/health`, `grep -E '^(API_SERVER|A2A)_' ~/.hermes/.env | cut -d= -f1`.
3. Runs API handoff: `POST /v1/runs` `{input, session_id}` + `Idempotency-Key` header -> `run_id`; poll `GET /v1/runs/{id}`, stream `/v1/runs/{id}/events`. Reusing `session_id` continues the transcript.
4. Enable inbound A2A (verified sequence):
   - back up `config.yaml` and `.env`
   - `hermes plugins enable a2a-platform` (bundled plugin, disabled by default)
   - `hermes config set gateway.platforms.a2a.enabled true`; `hermes config set gateway.platforms.a2a.extra.port 9900`
   - `.env`: `A2A_HOST=<tailnet IP>`, `A2A_PEER_TOKENS=pi:<secrets.token_urlsafe(32)>`, `A2A_TRUSTED_PEERS=pi`, `A2A_AGENT_NAME=...`, `A2A_PUBLIC_URL=http://<magicdns-name>:9900` (generate the token in-shell, never echo it)
   - `hermes gateway restart`, then verify: listener on :9900, `GET /.well-known/agent-card.json` shows the public URL, an authed `SendMessage` returns `TASK_STATE_COMPLETED`, and an unauthed POST returns 401. `~/.hermes/a2a_audit.jsonl` confirms which peer called.
5. Enable outbound (Hermes -> peer):
   - `hermes tools enable a2a --platform cli` (+ the user's other surfaces)
   - put the peer token in `.env` (e.g. `PI_A2A_TOKEN`) and reference it: `hermes config set a2a_agents.pi.auth.token '${PI_A2A_TOKEN}'` plus `.url`, `.auth.type bearer`, `.timeout`. The `not a recognized config key` warning is harmless; the plugin reads `a2a_agents` directly, and `${VAR}` refs expand.
   - verify with curl first (agent card, then authed `SendMessage`) because toolsets do not change inside the current session; the `a2a_call` tool is usable only in a NEW session.
   - Desktop and TUI sessions resolve toolsets from `platform_toolsets.cli` (plus surface toolsets); there is no separate desktop list to keep in sync. Never propose adding `a2a` to a desktop/other platform list to fix a desktop session — it is ignored.
   - If `a2a_*` tools are absent from the current session (check `tool_search` too), send via a one-shot CLI run, which loads plugin toolsets reliably: `hermes chat -Q -t a2a -q "Use a2a_call to send agent 'pi' this task: ..."` (smoke test: ask it to call `a2a_list`). Use this as the handoff path instead of telling the user it can't be done.
6. Pi side (pi-a2a) for Hermes -> Pi: dedicate one Pi instance as the inbound worker with fixed `server.workspace`, tailnet host, fixed port + `portFallback: 0`, `peerTokens {hermes: ...}`, `trustedPeers [hermes]`, `A2A_SERVER_ENABLED=true` only there (project `.pi/settings.json` cannot enable it). Use static peer entries; local registry/mDNS discovery does not span the tailnet.
7. Offer a caller-side 'handoff' skill: note = goal, state, repo/branch/PR, next steps, constraints.

## Pitfalls
- Files never travel: neither API nor A2A accept file uploads, so the handoff note must reference something reachable (git branch/PR, work item) or inline the content.
- Don't recommend `hermes mcp serve` by name alone; it is a messaging bridge.
- A2A refuses non-loopback binds without a token, and with no `A2A_TRUSTED_PEERS` every dispatch is 403; set both.
- Keep tokens out of `config.yaml` and out of git-synced Pi settings; pi-a2a stores `settings.json` tokens in plaintext, so prefer env/`.env.local`.
- If the user pastes a token into chat, still store it via `.env` reference and tell them to rotate it.
- pi-a2a `maxConcurrent` counts detached tasks for up to `asyncTimeoutSec` (24h default); stuck tasks block all inbound work.
- Restarting the gateway interrupts live platforms; it waits for in-flight turns, and `hermes gateway status` may warn the unit is outdated (restart refreshes it).
- To check whether a toolset actually reaches the agent, probe end-to-end with `hermes chat -Q -t <toolset> -q "call <tool>"` rather than importing Hermes internals in an ad-hoc script; the launcher's interpreter/path setup is hard to reproduce and import probes waste turns.
- Before claiming an outbound path is "not enabled", read `a2a_agents` and `platform_toolsets` in config.yaml; memory notes about A2A state go stale quickly.
