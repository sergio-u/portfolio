# SeatSearch ticket listings

Example event URL: `https://seatsearch.co/events/<event-id>`

## Scraping Strategy

SeatSearch is a fully client-side SPA. Scrapling's built-in fetchers (Fetcher, DynamicFetcher, StealthyFetcher) all return empty text because the page relies on deferred API polling and interactive elements. **Must use raw Playwright.**

### Key behaviors

1. **Marketplace polling:** After page load, SeatSearch queries multiple marketplace APIs (StubHub, Gametime, etc.) one by one. This takes ~15-20s. A loading spinner shows "Searching marketplaces... Checking [marketplace]..." during this phase.
2. **Quantity selector:** After results load, a "How many tickets?" prompt appears. Must click "1 ticket" (or desired qty) before listings render. Without this interaction, results may show "0 Tickets Available."
3. **Wait strategy:** Use `domcontentloaded` (not `networkidle` -- the page keeps connections open and will timeout). Then poll body text until the "Searching" / "Checking" messages disappear.

### Working snippet

```bash
cd ~/.openclaw/workspace/skills/scrapling
.venv/bin/python scripts/run.py << 'PYEOF'
from playwright.sync_api import sync_playwright

url = "https://seatsearch.co/events/<event-id>"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=60000)

    # Wait for marketplace search to finish (~15-20s)
    for i in range(45):
        page.wait_for_timeout(2000)
        text = page.inner_text("body")
        if "Searching marketplaces" not in text and "Checking" not in text:
            break

    # Select "1 ticket" if quantity prompt appears
    text = page.inner_text("body")
    if "How many tickets" in text:
        try:
            page.locator("text=1\nticket").first.click()
            page.wait_for_timeout(5000)
        except:
            pass

    # Extra settle time
    page.wait_for_timeout(5000)

    text = page.inner_text("body")
    print(text)

    browser.close()
PYEOF
```

### Parsing the output

Listings follow this pattern in the body text:
```
General Admission · Row GA
1-5 tickets available
Great Deal
$129
per ticket
```

Parse by splitting on "per ticket" blocks or matching `$\d+` values.

## Last checked

- **2026-03-18 23:36 PDT** -- 4 GA tickets: $129 (Great Deal), $139, $141 (Fair Price), $157 (Premium)
