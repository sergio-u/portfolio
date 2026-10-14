# hermes-personal

My [Hermes Agent](https://github.com/NousResearch/hermes-agent) profile: the
`~/.hermes` config, the skills and plugins I wrote for it, and the scripts that
keep it reproducible on a fresh machine. Hermes runs on a small Linux VM, reached
through Telegram, a web UI, and a dashboard on my tailnet, and it pairs with my
coding agent over A2A.

This is a sanitized copy for my portfolio. Memories, chat IDs, hostnames, and
personal IDs are removed or shown as placeholders such as `<telegram-chat-id>`.

## Highlights

- [`retrieval-system-design`](my-skills/software-development/retrieval-system-design/SKILL.md)
  is a design workflow for search, RAG, and knowledge graphs that starts from the
  workload, provenance, and authorization instead of a graph product. Its
  references cover chunking, permission-aware retrieval, and sizing.
- [`upstream-skill-ownership`](my-skills/software-development/upstream-skill-ownership/SKILL.md)
  and [`hermes-agent-local`](my-skills/autonomous-ai-agents/hermes-agent-local/SKILL.md)
  keep third-party skills pristine and put local behavior in companion skills,
  so upstream updates never conflict with my changes.
- [`hermes-memory-and-toolsets`](my-skills/autonomous-ai-agents/hermes-memory-and-toolsets/SKILL.md)
  records how I connected a self-hosted Hindsight memory server and how to
  diagnose provider tools that a platform's toolset settings hide.
- [`hermes-update-all`](scripts/bin/hermes-update-all) updates Hermes, hub
  skills, catalog plugins, and the web UI, then restarts and health-checks the
  services. `--check` only reports what is outdated.

## What's here

- `config.yaml`: main settings. No literal secrets; credentials are `${VAR}`
  references resolved from `.env`.
- `.env.example`: key names from `.env` with values stripped
  (`scripts/sync-env-example.py`).
- `SOUL.md`: persona and boundaries.
- `my-skills/`: skills I wrote or customized (`skills.create_dir`):
  - `autonomous-ai-agents/`: host and local administration, memory and
    toolset policy, and local overrides for the bundled Hermes skill
  - `software-development/`: retrieval system design (search, RAG, knowledge
    graphs, authorization) and upstream skill ownership
  - `productivity/todoist-workflow`, `research/reddit`
- `plugins/`: local plugins, `herdr-agent-state` (reports agent state to the
  Herdr terminal multiplexer) and `web/trafilatura` (article extraction backend).
- `manifests/`: reinstall lists, `hermes-pack.yaml` for catalog plugins
  (Hindsight memory, Home Assistant) and `skills-snapshot.json` for hub skills.
- `scripts/`: `sync-env-example.py`, `bin/hermes-update-all`, and copies of the
  systemd user units.

`skills/` keeps only pristine bundled and hub skills and is not tracked. Fixes to
bundled skills go in companion skills (for example `hermes-agent-local`), so
upstream updates never conflict with local changes.

## Never tracked

`.env`, `auth.json`, password and key files, databases, `sessions/`, `logs/`,
`cache/`, `tools/`, `installs/`, `hermes-agent/` (upstream source), skill
`.venv`/`node_modules`, and runtime state (OAuth caches, credentials, `data/`).

## Before committing

```sh
python3 scripts/sync-env-example.py   # after adding/removing .env keys
grep -nE '(token|key|secret|password|hash):\s*[^$ '"'"'"]' config.yaml   # should print nothing secret
hermes skills list-modified           # should be empty (skills/ stays pristine)
hermes plugins pack export > manifests/hermes-pack.yaml
hermes skills snapshot export manifests/skills-snapshot.json
```

## Restore on a new machine

1. Install Hermes, then clone this repo over `~/.hermes`.
2. `cp .env.example .env` and fill in values from the password manager.
3. Reinstall catalog plugins and hub skills from `manifests/`.
4. Re-authenticate OAuth providers (`hermes auth`, `gh auth login` for Copilot).
5. Install units: `cp scripts/systemd/*.service ~/.config/systemd/user/ &&
   systemctl --user daemon-reload && systemctl --user enable --now hermes-gateway
   hermes-dashboard hermes-webui`; `cp scripts/bin/hermes-update-all ~/.local/bin/`.
6. Clone nesquena/hermes-webui to `~/hermes-webui`. Re-create skill venvs as each
   SKILL.md describes.

## Services

- `hermes-gateway`: messaging gateway (Telegram)
- `hermes-dashboard`: 127.0.0.1:9119, exposed tailnet-only through Tailscale Serve
- `hermes-webui`: `~/hermes-webui`, 127.0.0.1:8787
- Update and restart everything: `hermes-update-all` (`--check`, `--restart`)
