---
name: upgrade-check
description: >
  Analyze OpenClaw releases between the current installed version and the latest available,
  check GitHub issue volume/rate trends, review the changelog for critical fixes and new features,
  and compare current config against new options. Use when the user says "should I upgrade",
  "upgrade check", "check for updates", "what changed since my version", "release notes",
  "is it safe to upgrade", "check openclaw updates", or "what's new in openclaw".
---

# OpenClaw Upgrade Check

Pre-upgrade analysis: issue health, changelog review, and config audit.

## Execution

This skill uses shell commands against the npm registry, GitHub API, and local OpenClaw CLI. No external scripts needed.

### Step 1: Gather Version Info

```bash
# Current installed version
openclaw --version

# Available versions (last 20)
npm view openclaw versions --json | jq -r '.[]' | tail -20

# Latest stable
npm view openclaw version
```

Identify the current version and the latest stable. If they match, report "already up to date" and skip to the config audit.

### Step 2: Issue Volume Analysis

Query GitHub API for weekly issue created/closed counts over the last 5 full weeks plus the current partial week. Compare the latest release window against prior windows to detect spikes.

```bash
# For each week window (adjust dates):
curl -s "https://api.github.com/search/issues?q=repo:openclaw/openclaw+is:issue+created:YYYY-MM-DD..YYYY-MM-DD" | jq '.total_count'
curl -s "https://api.github.com/search/issues?q=repo:openclaw/openclaw+is:issue+is:closed+closed:YYYY-MM-DD..YYYY-MM-DD" | jq '.total_count'
```

Also get per-release-window counts between each version from current to latest.

**Sleep 1s between API calls** to avoid GitHub rate limits (unauthenticated: 10 req/min for search).

**Report format:**
- Weekly trend table (created vs closed)
- Per-release window table
- Flag if latest window shows >30% spike in created issues vs the 4-week average
- Flag if close rate dropped significantly (ratio of closed/created < 0.3)

### Step 3: Changelog Review

Read the local changelog:

```bash
cat ~/.npm-global/lib/node_modules/openclaw/CHANGELOG.md
```

Extract all sections between the current installed version and the latest. If the changelog is truncated or missing versions, fall back to web:

```bash
# Fetch release notes from GitHub
curl -s "https://api.github.com/repos/openclaw/openclaw/releases" | jq '.[].tag_name'
```

Or fetch from the releases page:

```
https://github.com/openclaw/openclaw/releases
```

**Classify each change into:**

1. **Critical fixes** -- Security patches, data loss prevention, crash fixes, auth bypass fixes
2. **Relevant fixes** -- Bugs affecting our active channels/providers (check Reference section for what we use)
3. **New features** -- Notable new capabilities worth considering
4. **Nice-to-have** -- Minor improvements, provider additions we don't use, cosmetic changes

### Step 4: Config Audit

After reviewing the changelog for new config options or changed defaults:

```bash
# Current config snapshot
openclaw status

# Security audit
openclaw security audit

# Doctor check
openclaw doctor
```

Compare any new config options or changed behaviors mentioned in the changelog against the current setup. Flag:
- New security-related config that should be set
- Deprecated config that should be migrated
- New features that require opt-in config (like Active Memory, Dreaming, new providers)
- Changed defaults that might affect current behavior

## Output Format

Present findings as a structured upgrade report:

```
## Upgrade Report: <current> → <latest>

### Issue Health
[weekly trend + per-release data + any flags]

### Recommendation
[upgrade / wait / urgent based on the data]

### Critical Fixes (action required)
- [list with issue numbers]

### Relevant to Our Setup
- [fixes/features affecting our channels, providers, plugins]

### New Features Worth Enabling
- [with brief setup notes]

### Config Changes Needed
- [any config we should add/modify post-upgrade]

### Nice-to-Have
- [everything else, brief]
```

## Reference

### Our Active Setup

Keep this updated as the setup changes.

| Component | Value |
|---|---|
| Channels | Telegram, BlueBubbles |
| Providers | GitHub Copilot, LiteLLM |
| Plugins | acpx, searxng, bluebubbles, ocuclaw, github-copilot, litellm, memory-core, active-memory |
| Agents | main, claude, knowledge-base, homeassistant |
| Memory | memory-core, QMD, active-memory |
| OS | Debian Linux (cloud VM) |
| Node | v22 |
| Install | pnpm (npm registry) |
| Exec policy | security=full (main) |
| Gateway | LAN-bound (0.0.0.0), auth token |

> **Maintenance:** Update this table when channels, providers, or plugins change.

## Conventions

- Always present the issue health data before making an upgrade recommendation
- Classify changelog items relative to our active setup (Reference table above)
- If issue volume shows a significant spike with low close rate on the latest version, recommend waiting
- If critical security fixes exist, recommend upgrading regardless of issue volume
- Don't dump raw changelog -- summarize and categorize
- When recommending config changes, show the exact `openclaw config set` commands
- For Telegram output: use bullet lists, no markdown tables

## Requirements

- `openclaw` CLI installed
- `curl` and `jq` available
- Internet access for GitHub API and npm registry

## Troubleshooting

- **GitHub rate limit (403):** Unauthenticated search API allows ~10 req/min. Add `sleep 1` between calls. If still limited, reduce the number of weekly windows checked.
- **Changelog missing versions:** The local CHANGELOG.md may be truncated in npm builds. Fall back to `https://github.com/openclaw/openclaw/releases` or the web changelog.
- **`openclaw --version` format:** Returns something like `OpenClaw 2026.4.14 (hash)`. Parse the version number (e.g. `2026.4.14`) for comparisons.
