---
name: hermes-local-admin
description: "Use when changing local Hermes config or services."
---

# Hermes local admin (Sergio's install)

Covers: switching memory providers, per-platform toolsets, .env hygiene, running Hermes surfaces as systemd user services. Load the bundled `hermes-agent` skill too for general docs; this skill carries the local workflow.

## Always-on rules
- Inspect first (config, logs, server state), then present ONE concrete plan. Follow SOUL.md's confirmation rule: act without re-asking on clear, reversible changes Sergio explicitly requested (config edits, skill moves, commits to his private repo); ask first for destructive/hard-to-reverse steps, service or system changes, external/remote writes, and ambiguous scope. Approval prompts time out after ~1 min; if blocked, restate the exact command and wait — never retry silently.
- Don't flag, redact, or warn about credentials Sergio intentionally stores in private repos, .env, memories, or notes (he accepts the risk); just never print them or send them anywhere unrelated.
- Prefer the fix with the fewest moving parts: native Hermes features and existing config over generator scripts, git filters, or sync layers — every such layer Sergio has replaced with a native mechanism.
- Back up .env before editing (`cp .env .env.bak-$(date +%Y%m%d%H%M%S)`), then remind the user to delete the backup (it holds keys).
- Use `hermes config set` for scalar keys. For list edits it can't do, make minimal text edits (regex on the exact lines) — never round-trip config.yaml through ruamel/PyYAML dump, which reindents every list and buries the real change in a huge diff. Check `git diff config.yaml` shows only the intended lines.
- Never edit skills under ~/.hermes/skills/ (bundled/hub). Create or patch skills in ~/.hermes/my-skills/; local additions to a bundled skill go in its companion (e.g. hermes-agent-local).
- Python one-offs that import hermes-agent code must run on Hermes' runtime (`~/.hermes/tools/python-3*/bin/python3 -I` with hermes-agent on sys.path and `import hermes_bootstrap`), or use `hermes --run-module`; system python lacks its deps.
- Report in plain text (CLI, no markdown), short, with verified results.

## Diagnosing "tools X don't show up"
1. Grep the logs: `grep -h memory_manager ~/.hermes/logs/*.log | tail`. The line `configured but the 'memory' toolset is gated off` means the platform's toolset list lacks `memory` — the provider plugin is fine.
2. Check `platform_toolsets.<platform>` and `agent.disabled_toolsets` in config.yaml. Resolution: a saved platform list is exact (Blank Slate setups leave CLI minimal); unsaved platforms get full defaults; `agent.disabled_toolsets` removes globally, last.
3. `memory.memory_enabled` only governs the built-in MEMORY.md store — not provider tools. Don't propose it as the fix.
4. Fix by editing the single global list (see next section), not per-platform lists.

## Toolsets: declare once, everywhere (Sergio's standing preference)
- Sergio wants every tool available on every surface without keeping CLI/Telegram/WebUI in sync. Policy: NO `platform_toolsets.cli` / `.telegram` entries; all surfaces get Hermes' full default bundle minus `agent.disabled_toolsets`. Enable a tool everywhere = remove it from that list; disable = add it.
- WebUI resolves its tools via `_get_platform_tools(cfg, "cli")`, so it follows automatically.
- Don't use `hermes tools enable/disable --platform` or the interactive `hermes tools` save — it re-creates a per-platform list. If one reappears, delete it.
- Verify resolution with a Hermes-runtime script: `from hermes_cli.tools_config import _get_platform_tools; _get_platform_tools(load_config(), p, include_default_mcp_servers=False)` for cli and telegram — sets must match. `context_engine` drops out unless a non-default engine is configured (expected).

## Web search backend
- `web.backend` is the shared fallback; search uses `web.search_backend` and extraction `web.extract_backend` when set. Enabling the `web` toolset with only `web.backend: firecrawl` silently searches via Firecrawl keyless even if SEARXNG_BASE_URL is set — set `web.search_backend: searxng` too.
- Confirm the provider actually used from `logs/agent.log` (`Web search via <backend>`), not just that results came back.
- SearXNG endpoint: source of truth is `SEARXNG_URL` in `~/.hermes/.env` (read by the native searxng web_search provider) — don't hard-code it in skills. Probe with `curl "$URL/search?q=test&format=json"` before switching. (The hub `searxng-search` skill was removed: localhost-only upstream, redundant with native web_search.)
- Extraction: `web.extract_backend: trafilatura` via local plugin `plugins/web/trafilatura/` (runs fetch_page.py through `uv`; needs plugins.enabled `web/trafilatura`).
- Secrets: config.yaml holds only `${VAR}` refs; values live in .env. After adding/removing .env keys run `python3 scripts/sync-env-example.py` and commit `.env.example`.

## Config values of unknown origin / OpenClaw legacy
- When proposing a value already present in .env/config (URLs, hosts), say where it came from (grep .env, recovery/, backups/) and check it's reachable; old OpenClaw-era entries (e.g. netbird hosts) linger and may be dead. Don't present inherited values as recommendations.
- Legacy audit: grep config.yaml, .env, memories/, cron/jobs.json and my-skills for `netbird|openclaw|debian13-cloud|18789`; check `ps`/`ss -ltnp`/`tailscale serve status`/`systemctl --user list-unit-files | grep claw`; test hosts with a socket connect. Report as a numbered list grouped by risk, with a recommendation each; change nothing without approval, then apply ONLY the items Sergio approves (he often picks a subset — don't bundle the rest in). Deleting untracked files (old .env backups, recovery/, temp clones) is irreversible — always ask. Check for unused .env keys by grepping each key across config.yaml, my-skills, plugins and hermes-agent code.
- OpenClaw runs IN PARALLEL with Hermes by Sergio's choice: never stop/disable openclaw-gateway, remove its tailscale routes, or archive ~/.openclaw unless he asks. Migration is gradual, one skill at a time.
- OpenClaw-imported skills are NOT auto-loaded: they sit in ~/.hermes/archive/openclaw-imports-*/ (git-ignored). To migrate one: move it into my-skills/<category>/, repoint every `~/.openclaw/...` path (venvs, .env, credentials) to Hermes locations (keys into ~/.hermes/.env, venv inside the skill dir), verify `hermes skills list`, restart services, commit. Prefer replacing with a hub/bundled equivalent when one exists.

## Skill pruning (built-in skills)
- Disable via the `skills.disabled` list in config.yaml (minimal text edit, sorted); verify with `hermes skills list | tail -1`, restart, commit.
- Judge relevance by Sergio's actual usage profile, not generic taste: the OpenClaw skills dir (`ls ~/.openclaw/workspace/skills`) shows a personal, remote, HEADLESS workspace — travel, food, music/media, todo/notes, home automation, light coding. Disable office docs (docx/xlsx/pptx), ML training/model tooling, creative/design, games, desktop-only tools, jailbreak tools, work-only pipelines.
- Before disabling, check for retired bundled copies still loading from skills/ (see references/git-tracking.md) and archive those instead.

## Config parity with hermes-work
- Diff flattened YAML (Hermes-runtime ruamel safe-load both files) and ignore default-only noise; surface only behavior differences. Adopted from work: `display.busy_input_mode: queue` (mid-turn messages wait instead of interrupting; also `/busy queue`), `tool_loop_guardrails`, `display.busy_ack_detail`/`long_running_notifications`, `cron.catch_up_missed`. Keep personal on update channel `stable` unless asked; model/reasoning follow Sergio's latest explicit choice (`model.default`, `agent.reasoning_effort`).
- `memory.memory_enabled` / `user_profile_enabled` false means memories/MEMORY.md and USER.md are NOT loaded into sessions at all; clean MEMORY.md (entries separated by `§`, facts not instructions) before enabling.

## Verifying a change
- The current conversation's tool schemas are frozen at session start; a restart doesn't help it. Verify in a fresh process:
  `timeout 240 hermes chat -q "Call <tool> ... Do not use terminal."` then re-grep the log for `registered (N tools)`.
- `hermes tools --summary` needs an interactive TTY; read platform_toolsets from config.yaml instead.

## Memory provider: Hindsight (self-hosted)
See `references/hindsight-self-hosted.md`.

## Dashboard / hermes-webui as permanent services
See `references/dashboard-service.md` (units, public_url + basic auth fix for the Host-header 400, webui install, verification curls). Bind 127.0.0.1, expose via `tailscale serve` on its own HTTPS port per service — not a public reverse proxy.

## Persona / communication-style changes
- SOUL.md is the standing behavior source; edits change default behavior, so get approval, change only the intended paragraph, show the full diff, and tell Sergio it changed. Restart services so Telegram/WebUI load it; the current CLI session won't.
- Adapting rules from other agents' files (OpenClaw SOUL/AGENTS/USER, Pi AGENTS.md, hermes-work SOUL): see `references/behavior-files.md` for the quality bar and placement table. Sergio wants a high bar — propose few, evidence-backed changes, not a long list.
- Style skills (e.g. i-have-adhd) are hub installs: `hermes skills install <identifier> --category <cat> --yes`, read the scan verdict and the full SKILL.md, then wire it via a SOUL.md paragraph (load at session start, keep upstream unmodified, off-switch phrases). Resolve conflicts with SOUL/Boundaries in the SOUL wording, not by editing the skill (e.g. invented time estimates vs "admit uncertainty"; act-don't-ask vs confirm-before-writes). Re-export the skills snapshot, restart, verify in a fresh `hermes chat -q`, commit.

## Generating secrets
Never print generated passwords/keys in chat (auto-retain stores turns in Hindsight). Generate inside a script, write to a 0600 file for Sergio to move into his password manager, store only hashes in .env, and log in for tests by reading the file into a shredded temp JSON.

## Git-tracking ~/.hermes (private backup repo)
See `references/git-tracking.md`: track config, my-skills/ (`skills.create_dir`; skills/ stays pristine bundled+hub, fixes go in companion skills like hermes-agent-local), local plugins, scripts/ (systemd unit copies, update script, sync-env-example.py), .env.example, manifests/; exclude sessions/DBs/caches/deps. Same policy as the hermes-work repo — keep them aligned. Key traps: `hermes config get` masks secrets as `***`; skills dirs hold OAuth creds as dotfiles. Push only to the private remote the user names.

## Updating Hermes + gateway + dashboard + webui
- `hermes update` updates the agent install (gateway AND dashboard share it) and restarts only the gateway; webui (~/hermes-webui) is a separate git clone: `git pull --ff-only` (if history was rewritten upstream and no local edits: `git reset --hard origin/master`).
- Restart all three afterwards (`systemctl --user restart hermes-gateway hermes-dashboard hermes-webui`) — webui imports agent code. Health: dashboard 127.0.0.1:9119 (302), webui 127.0.0.1:8787/health.
- `~/.local/bin/hermes-update-all` (copy in scripts/bin/ — keep identical, commit both) does this. Targets `--hermes --skills --plugins --webui` (none = all); options `--check`, `--restart`, `--no-restart`, `--reset-webui`. Steps: `hermes update --no-gateway-restart`; `hermes skills update` + snapshot export; `hermes plugins check-updates --json` → `hermes plugins update <name>` per outdated plugin (no update-all); webui ff-only pull; re-pin `HERMES_WEBUI_PYTHON` in ~/hermes-webui/.env from `installs/*/facts.json` venv BEFORE restart (plugin/agent updates rebuild the venv; stale path = webui crash loop); restart + health. Real runs restart the gateway (kills in-flight Telegram turns) — fine from CLI when Sergio asked; run long with background+notify.
- `hermes skills update` skips hub skills with local edits. Before forcing, diff the installed copy against a fresh clone of the upstream source (identifier in `skills/.hub/lock.json`) and report what the edits do; if the skill is redundant with a native feature, recommend uninstall (`hermes skills uninstall <name>`, re-export snapshot, drop its now-unused .env keys + sync .env.example) over forking.
- `hermes config set` warns "unrecognized key" for `agent.reasoning_effort`; it's valid (what `/reasoning` writes) — ignore.
- Dashboard/webui units are hand-written (no install command exists); only `hermes gateway install` generates a unit. Hand units hard-code node/npm PATH versions — re-check after updates.
