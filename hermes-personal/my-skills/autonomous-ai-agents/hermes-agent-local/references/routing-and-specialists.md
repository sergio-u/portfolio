# Routing turns to specialist models/agents

Use when the user asks about per-message model routing, fast paths for quick commands, specialist subagents, or Jev-style decision routers. Verify against `~/.hermes/hermes-agent/website/docs/` before answering; grep the docs tree, not just `features/delegation.md`.

## Native mechanisms (check in this order)

| Need | Mechanism | Doc |
|---|---|---|
| Named specialist with own model, SOUL, skills, toolsets, MCP | **Profile**; shown in desktop as a **Bot Mode Bot** | `user-guide/bot-mode.md`, `user-guide/profiles.md` ("Profiles, agents, and bots") |
| One fast model for a whole chat/channel | `platforms.<p>.channel_overrides` (model/provider/system_prompt; `/model` wins) | `user-guide/messaging/index.md` |
| Route a chat/user to a profile on one shared bot | `gateway.multiplex_profiles: true` + `gateway.profile_routes` (by chat/user/guild id, not content) | `user-guide/multi-profile-gateways.md` |
| One messaging bot per specialist, one gateway | per-profile bot token + multiplexing | same |
| Cheaper workers for background jobs | `delegation.model/provider` (global, no per-task model or toolsets) | `features/delegation.md` |
| Built-in side jobs on other models | `auxiliary.*` slots | `user-guide/configuration.md` |

Pitfalls:
- Do not answer "Hermes has no specialist agents" from delegation docs alone — Bot Mode/profiles are the specialist primitive; `delegate_task` children are generic.
- `message_agent` (bot-to-bot) is fire-and-forget and only exists in a session titled exactly `Bot Chat` on an install where some `profile.yaml` has `ui_meta: hermes-bots`; headless installs must add both markers by hand.
- For speed, the router must run BEFORE the main model; main-model delegation adds a slow call before and after.
- Switching models mid-conversation breaks prompt cache; route only at clear task boundaries.
- Plugin seams: `pre_llm_call` (adds context) and `llm_request` middleware (rewrites request) both receive `platform=`, so platform-scoped routing is possible; neither is known to skip the agent turn — verify a turn-takeover hook in source before promising content-based dispatch to another profile.
- Plugins can swap model, not provider connection.

## Recommended shape for fast quick-commands (user's priority: speed)

1. One messaging bot per specialist profile (small model, only its tools, short SOUL) on a multiplexed gateway — user picks the chat, zero misroutes, follow-ups keep history.
2. Plugin slash commands for the most frequent no-LLM actions (HA Assist passthrough, Todoist Quick Add).
3. Content-based router (Jev / local Laya) only later, Telegram-only, shadow mode first, low confidence -> main agent.

## Jev ecosystem notes

- Jev (TypeSafe) is a hosted decision model: typed choice/score/yes-no, never generates text or extracts slots. Laya is the open-source, local, wire-compatible alternative (preferred for this user).
- Healthiest Hermes integration: `kerpopule/hermes-jev-skills` (routing pools by tier x work-kind, shadow mode, skill selection). Avoid Jev context compaction (cache breakage, state loss, data leaves machine).
- r/hermesagent had launch-era spam around Jev; weight GitHub health signals over hype.
- Evaluate project health with `gh repo view --json stargazerCount,forkCount,pushedAt,createdAt,licenseInfo` plus contributor/PR counts via `gh api`; `gh search repos` for discovery. Read READMEs via `gh api repos/O/R/readme -H 'Accept: application/vnd.github.raw'` without cloning.
