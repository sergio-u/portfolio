# Adapting behavior rules into Hermes (SOUL.md / memories / skills)

Sources seen: OpenClaw workspace (~/.openclaw/workspace: SOUL.md, AGENTS.md, USER.md, MEMORY.md, IDENTITY.md, DREAMS.md), Pi user-level AGENTS.md (~/Documents/pi-config/AGENTS.md, mostly work coding), hermes-work SOUL.md.

## Quality bar (apply to every candidate before proposing it)
1. Changes behavior: fixes a failure or gap actually observed (cite the evidence from this install/session), not just a nice principle.
2. Not already covered by Hermes. Check `hermes-agent/agent/prompt_builder.py` before proposing: PLATFORM_HINTS already forbid tables on Telegram/WhatsApp; SESSION_SEARCH_GUIDANCE already says search past sessions; build_memory_guidance already says skills-first, memory as declarative facts, consolidate when full.
3. Right home:
   - SOUL.md: identity, standing behavior, boundaries (always-on).
   - memories/USER.md / MEMORY.md: facts needed in EVERY session, written as declarative facts, not imperatives.
   - Skills: task-class procedures and pitfalls (e.g. commit hygiene goes in git-tracking.md, not SOUL).
   - Hindsight: task-specific personal facts (travel style, editor/VCS setup, digest format, music taste).
4. Doesn't reference tools/hosts that don't exist here (e.g. a `trash` rule when trash isn't installed, OpenClaw automations, CDP hosts).

Prefer merging into an existing SOUL line over adding a new rule. Rules Sergio found irrelevant (e.g. "don't promise to remember unless written") get dropped, not argued.

## Usually reject
- Persona identity files (IDENTITY.md name, DREAMS.md diary), platform-specific tool conventions, work-coding rules (ASCII/EOL/GUID, PowerShell, jj, Sourcegraph).
- Pi's "dynamic verification only when asked": on this install live tests (fresh `hermes chat -q` + log grep) are what catch silent misrouting — keep verifying.

## Usually worth taking (already applied to SOUL.md)
- Scoped confirmations (act on clear reversible requested changes; ask for destructive/system/external/ambiguous).
- Credential-storage acceptance (from Pi AGENTS.md).
- Deliver requested scope; don't silently narrow/widen/replace.
- Fewest moving parts.
- Explicitly correct earlier wrong statements that affect decisions.

## memories/ hygiene
OpenClaw-era MEMORY.md accumulated raw conversation transcript lines as "memories"; these load every session. Prune to atomic facts; move task-specific facts to Hindsight.
