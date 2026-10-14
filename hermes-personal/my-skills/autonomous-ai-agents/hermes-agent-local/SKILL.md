---
name: hermes-agent-local
description: "Use with hermes-agent for this install's local notes: A2A/Pi, audits, memory checks, overrides."
---

# Hermes Agent — local companion

Companion to the bundled `hermes-agent` skill, which stays pristine so `hermes update` can refresh it. Load `hermes-agent` first, then this for local additions. When the two conflict, prefer this skill but recheck live docs/installed source.

| Task | Reference |
|------|-----------|
| Agent-to-agent with Pi, Claude Code, remote Hermes (either direction): API server, A2A enable/verify, outbound `a2a_agents`, Pi packages | `references/inbound-agent-interfaces.md` |
| Compare other agent workspaces for selective adoption | `references/agent-workspace-audits.md` |
| Validate memory capture, storage, recall and history search | `references/memory-validation.md` |
| Per-message/per-platform model routing, specialist profiles/Bots, multiplexed bots, Jev/Laya routers | `references/routing-and-specialists.md` |
| Corrections to bundled references (delegate_task shape, cron limits, AGENTS.md discovery, desktop toolsets, `Skill '' not found` / Copilot duplicate calls) | `references/local-overrides.md` |

Local fixes to the bundled skill go here, never into `~/.hermes/skills/autonomous-ai-agents/hermes-agent/`.
