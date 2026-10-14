---
name: scrapling
description: >
  Scrape websites, extract data, and fetch web content using Scrapling with stealth capabilities.
  Use when the user says "scrape website", "extract data from page", "bypass anti-bot",
  "web scraping", "fetch", "get prices from", "parse", "crawl", or "monitor" a website.
  Supports plain HTTP fetching, JS-rendered pages, anti-bot bypass (Cloudflare, Turnstile),
  CSS/XPath selectors, and StealthyFetcher for protected sites. NOT for simple page reading
  or article extraction (use trafilatura), browser UI interaction like clicking through flows
  (use agent-browser), or MCP-based scraping.
---

# Scrapling

Run web scraping operations via Python snippets backed by Scrapling in a local uv venv.

## Execution

All snippets run via `.venv/bin/python scripts/run.py` from the skill directory. The runner pre-imports all fetchers and always exits cleanly -- required to prevent the Telegram session from hanging on browser processes.

**Never use bare `python` or `python3`** -- scrapling is not on the system path.

**Inline (single line):**
```bash
cd ~/.openclaw/workspace/skills/scrapling
.venv/bin/python scripts/run.py 'page = Fetcher.get("https://example.com"); print(page.css("h1::text").get())'
```

**Multi-line (heredoc):**
```bash
cd ~/.openclaw/workspace/skills/scrapling
.venv/bin/python scripts/run.py << 'PYEOF'
page = StealthyFetcher.fetch("https://example.com", headless=True, network_idle=True)
for item in page.css(".product-name"):
    print(item.text)
PYEOF
```

## Fetching Strategy

Always start with the lightest fetcher and only escalate if it fails or the user requests it:

1. **`Fetcher.get(url)`** -- plain HTTP, TLS spoofing, fastest. Try this first.
2. **`DynamicFetcher.fetch(url)`** -- Playwright Chromium, JS rendering. Use if content is JS-rendered.
3. **`StealthyFetcher.fetch(url, headless=True)`** -- Camoufox Firefox, full stealth. Use if blocked or Cloudflare/anti-bot detected.

**Signs of a block** (escalate to next fetcher): HTTP 403/429/503, page contains "just a moment", "access denied", "cloudflare", "captcha", or the content is mostly empty/boilerplate.

**API note:** `Fetcher` uses `.get()` / `.post()`. `StealthyFetcher` and `DynamicFetcher` use `.fetch()`. Sessions use `.fetch()` for browser-backed or `.get()` / `.post()` for HTTP-backed.

See `references/api.md` for full selector, fetcher, and session API reference.

## Conventions

- Start with `Fetcher.get()` -- only escalate if blocked or content is missing
- Always `print()` results -- the runner has no implicit display
- Use `.text` for clean text, `.attrib["href"]` for attributes
- Limit large result sets with `[:10]` to keep output readable
- Confirm before destructive or high-volume operations (bulk scraping, writing to files)
- Summarize results cleanly -- present extracted data in structured format, not raw HTML
- Use machine-readable output (JSON, CSV) when results will be parsed downstream

## Requirements

- uv with a local `.venv` in the skill directory
- `scrapling[all]` and `camoufox[geoip]` installed in the venv
- Playwright Chromium browser installed (for DynamicFetcher)
- Camoufox browser fetched (for StealthyFetcher)

### Setup (first run only)

Scrapling is installed only inside the skill's local uv venv -- never system-wide. All commands must use `.venv/bin/python` explicitly.

Check if ready:
```bash
test -f ~/.openclaw/workspace/skills/scrapling/.venv/bin/python && echo "ready" || echo "needs setup"
```

If not ready:
```bash
cd ~/.openclaw/workspace/skills/scrapling
uv venv .venv
uv pip install --python .venv "scrapling[all]" "camoufox[geoip]"
.venv/bin/python -m playwright install chromium
.venv/bin/python -m camoufox fetch
```

If playwright or camoufox install fails, check for missing system libraries:
```bash
.venv/bin/python -m playwright install-deps chromium
```

## Troubleshooting

### Fetcher returns empty/blocked content
Escalate: try `DynamicFetcher.fetch()`, then `StealthyFetcher.fetch(url, headless=True, network_idle=True)`.

### StealthyFetcher hangs or times out
Add `network_idle=True` if not already set. Check that camoufox browser is fetched: `.venv/bin/python -m camoufox fetch`.

### Import errors
Venv may be incomplete. Reinstall: `uv pip install --python .venv "scrapling[all]" "camoufox[geoip]"`.

### Browser launch fails
Missing system deps. Run: `.venv/bin/python -m playwright install-deps chromium`.
