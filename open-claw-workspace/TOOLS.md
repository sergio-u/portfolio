# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## Conventions

- **Cron / scheduled jobs:** When Sergio says "add a job", "cron job", "schedule this", or "set a reminder" -- always use `openclaw cron`, never Linux crontab or `at`.

## OpenClaw

- **Subagents:** Delegate only sizeable independent work. Use named tiers (`small`, `medium`, `large`); never spawn verification agents or Discord threads unless requested.
- **Telegram group/topic replies:** If replies disappear after upgrades, check `messages.groupChat.visibleReplies`; this workspace uses `automatic`.
- **Owner chat commands:** Owner-level chat commands require `commands.ownerAllowFrom`; check this if restart/admin commands stop working from chat.

## Ad hoc code / shell hygiene

- Run the smallest check that proves the change; inspect exact generated input after a repeated failure.

## Browser (agent-browser)

- **When to use CDP:** Only for authenticated or Cloudflare-protected sites (Amazon reviews, camelcamelcamel, etc.). For unauthed scraping, prefer Scrapling Fetcher — it's faster and lighter.
- **CDP endpoint:** Remote Chrome at `<home-server>:9222` (Chrome 147, Camelizer extension installed).
  - WebSocket UUID changes on Chrome restart — always fetch dynamically:
    ```bash
    WS_URL=$(curl -s http://<home-server>:9222/json/version | jq -r '.webSocketDebuggerUrl')
    npx agent-browser --cdp "$WS_URL" open <url>
    ```
  - Authenticated sessions (e.g. Amazon) are available in the browser profile. New tabs opened via browser-level CDP inherit cookies.
- **Local headless** works but is slower. Use only as fallback if CDP is unreachable.
- **Always close sessions** when done: `npx agent-browser close`

## Amazon Safety

- Amazon uses Sergio's main account. Never click Buy Now. Cart changes require explicit confirmation; never modify pre-existing cart items without confirmation.

## Web Search

- **Provider:** SearXNG (bundled plugin, configured in `plugins.entries.searxng`)
- **Instance:** `http://<searxng-host>:8081` (self-hosted, private mesh network)
- **Usage:** Use the built-in `web_search` tool directly -- no curl workaround needed
- **Fallback:** If `web_search` fails, use `exec` + `curl` against the same URL with `format=json`

## Dependency Updates

Skills use different package strategies. Here's how to update each:

### Auto-updating (no action needed)
- **uv inline scripts** (flights, reddit, tidal, trafilatura, youtube-transcript, annas-archive, pdf-analyzer, knowledge-base) — uv resolves latest on each run
- **gws CLI** — `npx @googleworkspace/cli@latest` always fetches latest
- **agent-browser** — `npx agent-browser` always fetches latest

### Manual update (venvs)
```bash
# scrapling
cd ~/.openclaw/workspace/skills/scrapling
uv pip install --python .venv --upgrade "scrapling[all]" "camoufox[geoip]"

# splitwise
cd ~/.openclaw/workspace/skills/splitwise
uv pip install --python .venv --upgrade splitwise requests requests-oauthlib
```

### Manual update (git-managed skills)
```bash
# gws sub-skills (symlinked from repo)
cd ~/.openclaw/workspace/skills/gws/.gws-repo && git pull
```

### Adding gws sub-skills
```bash
cd ~/.openclaw/workspace/skills/gws
ln -s .gws-repo/skills/gws-<name> gws-<name>
```

### Audit outdated packages
```bash
# Check all venvs at once
for dir in ~/.openclaw/workspace/skills/*/; do
  [ -d "$dir/.venv" ] && echo "--- $(basename $dir) ---" && uv pip list --python "$dir/.venv" --outdated 2>/dev/null | tail -n +3
done
```
