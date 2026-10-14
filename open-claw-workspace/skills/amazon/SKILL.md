---
name: amazon
description: >
  Search Amazon products, compare options, analyze reviews, check price history,
  and make purchase recommendations. Also reviews the Amazon cart for impulse buys.
  Use when the user says "find on amazon", "amazon search", "compare products",
  "check reviews", "is this a good price", "should I buy", "find me a",
  "amazon product", "price history", "best option for", "check my cart",
  "review my amazon cart", "impulse buy check", "audit my cart",
  or asks to research a purchase decision on Amazon.
---

# Amazon Product Research

Search, compare, and analyze Amazon products using a multi-tool pipeline optimized for speed and data richness.

## Safety Rules

### Permissions: Read + Cart Only

This skill can **browse, extract, analyze, and manage the cart**. It must **NEVER purchase anything**.

**ALLOWED — Cart operations (with confirmation):**
- **Add to Cart** — only after showing the user exactly what will be added (product name, ASIN, price, quantity) and receiving explicit confirmation
- **Remove from Cart** — only after listing the item and receiving explicit confirmation
- **Modify quantity** of items already in cart — only after showing current vs proposed quantity and receiving confirmation

**NEVER do any of the following:**
- Click "Buy Now", "Buy Now with 1-Click", or any instant purchase button
- Click "Place your order" or any checkout/payment confirmation
- Click "Subscribe & Save" or enroll in any subscription
- Submit any payment, address, or gift card form
- Modify account settings, wishlists, saved addresses, or payment methods
- Proceed past the cart page into checkout flow

**Key distinction:** "Add to Cart" ≠ "Buy Now". Adding to cart is a staging action with no payment. "Buy Now" triggers immediate purchase. Only the former is allowed, and only with explicit user confirmation per item.

**Cart operation protocol:**
1. State what you're about to do (add/remove/modify, product name, ASIN, price, quantity)
2. Wait for user confirmation ("yes", "do it", "go ahead", etc.)
3. Execute the action
4. Confirm the result ("Added X to cart" / "Removed X from cart")

**Pre-existing cart items:** Never remove or modify quantity of items already in the cart unless the user explicitly asks. When auditing the cart, only suggest changes — never execute without confirmation.

## Execution

This skill combines multiple tools across phases. Always start with the lightest approach and escalate only when needed.

### Phase 1: Discovery (Search Results)

Use Scrapling Fetcher — plain HTTP, ~1.3s, returns up to 60 structured results.

```bash
cd ~/.openclaw/workspace/skills/scrapling
.venv/bin/python scripts/run.py << 'PYEOF'
import json
page = Fetcher.get("https://www.amazon.com/s?k=SEARCH+TERMS")
items = page.css('[data-component-type="s-search-result"]')
results = []
for item in items:
    asin = item.attrib.get("data-asin", "")
    if not asin:
        continue
    results.append({
        "asin": asin,
        "title": item.css("h2 span::text").get(""),
        "price": item.css(".a-price .a-offscreen::text").get(""),
        "rating": item.css("span.a-icon-alt::text").get(""),
        "img": item.css("img.s-image::attr(src)").get(""),
    })
print(json.dumps(results, indent=2))
PYEOF
```

For broader results, run multiple searches with different keywords in parallel.

### Phase 2: Product Detail

Use Scrapling Fetcher on `/dp/<ASIN>` — ~2.5s, returns full structured data including hi-res images.

```bash
cd ~/.openclaw/workspace/skills/scrapling
.venv/bin/python scripts/run.py << 'PYEOF'
import json, re
page = Fetcher.get("https://www.amazon.com/dp/ASIN_HERE")
# Hi-res images from inline scripts
hi_res = []
for s in page.css("script::text").getall():
    hi_res.extend(re.findall(r'"hiRes"\s*:\s*"(https://[^"]+)"', s))
data = {
    "title": page.css("#productTitle::text").get("").strip(),
    "price": page.css(".a-price .a-offscreen::text").get(),
    "rating": page.css("#acrPopover span.a-icon-alt::text").get(),
    "review_count": page.css("#acrCustomerReviewText::text").get(),
    "bullets": [b.text.strip() for b in page.css("#feature-bullets li span.a-list-item")],
    "brand": page.css("#bylineInfo::text").get("").strip(),
    "availability": page.css("#availability span::text").get("").strip(),
    "images": hi_res[:6],
}
print(json.dumps(data, indent=2))
PYEOF
```

### Phase 3: Reviews

**Quick mode (no auth, bundled with product page):**

Extract ~10 top reviews embedded on the product page. Add this to the Phase 2 script:

```python
reviews = []
for r in page.css('[data-hook="review"]')[:10]:
    reviews.append({
        "title": r.css('[data-hook="review-title"] span::text').getall()[-1] if r.css('[data-hook="review-title"] span::text').getall() else None,
        "rating": r.css('[data-hook="review-star-rating"] span.a-icon-alt::text').get(),
        "body": r.css('[data-hook="review-body"] span::text').get("").strip()[:300],
        "verified": bool(r.css('[data-hook="avp-badge"]')),
    })
```

**Deep mode (requires auth via CDP):**

Use agent-browser connected to authenticated Chrome for paginated, filterable reviews.

```bash
# Get CDP WebSocket URL (UUID changes on Chrome restart)
WS_URL=$(curl -s http://CDP_HOST:CDP_PORT/json/version | jq -r '.webSocketDebuggerUrl')

# Open reviews page
npx agent-browser --cdp "$WS_URL" open "https://www.amazon.com/product-reviews/ASIN?reviewerType=all_reviews&sortBy=recent" 2>&1
npx agent-browser wait --load networkidle 2>&1
```

Extract via eval:

```bash
npx agent-browser eval --stdin <<'EVALEOF'
JSON.stringify({
  reviews: Array.from(document.querySelectorAll('[data-hook="review"]')).map(r => ({
    title: (() => { const spans = r.querySelectorAll('[data-hook="review-title"] span'); return spans[spans.length-1]?.innerText; })(),
    rating: r.querySelector('[data-hook="review-star-rating"] span')?.innerText,
    date: r.querySelector('[data-hook="review-date"]')?.innerText,
    body: r.querySelector('[data-hook="review-body"] span')?.innerText?.slice(0, 500),
    verified: !!r.querySelector('[data-hook="avp-badge"]'),
    helpful: r.querySelector('[data-hook="helpful-vote-statement"]')?.innerText,
    author: r.querySelector('.a-profile-name')?.innerText,
    hasImages: r.querySelectorAll('.review-image-tile').length > 0,
  })),
  totalRatings: document.querySelector('[data-hook="total-review-count"]')?.innerText,
  overallRating: document.querySelector('[data-hook="rating-out-of-text"]')?.innerText,
})
EVALEOF
```

**Deep mode URL parameters:**
- `sortBy=recent` or `sortBy=helpful`
- `filterByStar=critical` (1-3 stars), `five_star`, `four_star`, `one_star`, `positive`
- `pageNumber=N` for pagination
- `filterByKeyword=WORD` for keyword search within reviews

### Phase 4: Image Analysis

Download hi-res images (URLs extracted in Phase 2) and analyze with vision model:

```bash
curl -s -o /tmp/product-img-1.jpg "IMAGE_URL_HERE"
```

Then use the `image` tool to assess material quality, size cues, build quality, and use-case fit.

### Phase 5: Price History

Use agent-browser CDP on camelcamelcamel (Cloudflare blocks plain HTTP):

```bash
WS_URL=$(curl -s http://CDP_HOST:CDP_PORT/json/version | jq -r '.webSocketDebuggerUrl')
npx agent-browser --cdp "$WS_URL" open "https://camelcamelcamel.com/product/ASIN" 2>&1
npx agent-browser wait --load networkidle 2>&1
npx agent-browser wait 2000 2>&1
npx agent-browser eval --stdin <<'EVALEOF'
const table = document.querySelector('table')?.innerText || 'no data';
const chart = Array.from(document.querySelectorAll('img')).find(i => i.src?.includes('charts.camelcamelcamel'))?.src || 'no chart';
'TABLE: ' + table.replace(/\n/g, ' | ') + '\nCHART: ' + chart;
EVALEOF
```

The chart image URL is public — download and analyze with vision model for trend visualization:

```bash
curl -s -o /tmp/price-chart.png "https://charts.camelcamelcamel.com/us/ASIN/new.png?force=1&zero=0&w=1022&h=529&desired=false&legend=1&ilt=1&tp=all&fo=0&lang=en"
```

### Phase 6: External Reviews (Optional)

Use SearXNG for YouTube reviews, blog posts, Reddit threads:

```bash
curl -s "http://<searxng-host>:8081/search?q=PRODUCT+NAME+review&format=json" | jq '.results[:5]'
```

Or with `site:reddit.com` for community opinions.

## Workflow

For a typical product research request:

1. **Clarify requirements** — what's it for, priorities (price, quality, portability, etc.)
2. **Discovery** — search with 1-2 keyword variations, collect candidates
3. **Filter** — eliminate irrelevant results (wrong category, too expensive, low ratings)
4. **Detail** — fetch product pages for top 3-5 candidates (parallel)
5. **Quick reviews** — use embedded reviews from product pages for initial signal
6. **Image analysis** — download and assess product images for the most promising options
7. **Deep reviews** — if needed, use CDP for critical/filtered reviews on top picks
8. **Price history** — check camelcamelcamel for top 2-3 picks
9. **Recommend** — present findings with clear winner + alternatives, with reasoning

Skip steps that aren't needed. Quick searches may only need phases 1-3.

### Cart Impulse Buy Analysis

When the user asks to review their cart, check for impulse buys, or audit purchases:

1. **Fetch cart** via authenticated CDP browser:
   ```bash
   WS_URL=$(curl -s http://<home-server>:9222/json/version | jq -r '.webSocketDebuggerUrl')
   npx agent-browser --cdp "$WS_URL" open https://www.amazon.com/gp/cart/view.html
   npx agent-browser wait --load networkidle
   npx agent-browser snapshot -i
   ```
2. **Extract items** from the snapshot -- product names, quantities, and subtotal.
3. **Close browser** immediately after extraction (`npx agent-browser close`). Cart is read-only.
4. **Evaluate each item** using these criteria:
   - **Consumable or replacement?** (film, supplements, bulbs) → likely not impulse
   - **Solves an active problem?** Ask: "Is the user dealing with this annoyance right now?" → legit
   - **Aspirational purchase?** Bought for a future version of yourself ("I'll start doing X") → likely impulse
   - **Already owns something that works?** → impulse unless the upgrade is clearly justified
   - **Specific use case nameable?** If the user can name exactly when/where they'd use it → legit
5. **Present verdict** for each item:
   - Clear keep, drop, or interrogate
   - One-line reasoning
   - If interrogating, ask the user a pointed question ("When did you last...?", "What specifically would you use this for?")
6. **Summarize** with a suggested trimmed cart and estimated savings.

**Trigger phrases:** "check my cart", "review my amazon cart", "impulse buy check", "should I buy this cart", "audit my cart"

**Tone:** Be direct and honest. The user is asking you to challenge them, not validate. If something looks like an impulse buy, say so -- but accept their reasoning if they push back with a concrete use case.

## Reference

### CDP Configuration

| Setting | Value |
|---------|-------|
| CDP Host | `<home-server>` |
| CDP Port | `9222` |
| Version endpoint | `http://<home-server>:9222/json/version` |
| Connection | `--cdp "$(curl -s http://<home-server>:9222/json/version \| jq -r '.webSocketDebuggerUrl')"` |

> **Maintenance:** Update host/port if the remote Chrome instance changes. The WebSocket UUID changes on Chrome restart — always fetch it dynamically.

### ASIN Cache

| Product | ASIN | Price (when checked) | Notes |
|---------|------|---------------------|-------|
| | | | |

> **Maintenance:** Add entries as products are researched for quick re-lookup.

## Conventions

- **Read + Cart only.** Never click purchase, checkout, subscribe, or account modification buttons. Cart add/remove/modify is allowed with explicit user confirmation per item (see Safety Rules).
- Confirm with the user before deep-diving more than 5 products (to manage time/tokens).
- Present results as clean summaries — don't dump raw JSON or HTML.
- When comparing products, use bullet lists (no markdown tables — this runs on Telegram).
- Include direct Amazon links as `https://www.amazon.com/dp/ASIN` for easy access.
- For price history, state whether current price is near the low, mid, or high of its range.
- If a search returns irrelevant results (standing desks when looking for book stands), narrow keywords automatically.
- Always close agent-browser sessions when done: `npx agent-browser close`.
- Download images to `/tmp/` for analysis, not the workspace.

## Authentication

- **Amazon browsing:** No auth needed for search and product pages (Scrapling Fetcher).
- **Amazon reviews (deep):** Requires user to be signed in on the remote Chrome instance. Verify by checking for "Hello, [Name]" on Amazon homepage via CDP.
- **camelcamelcamel:** No auth needed (pages load via CDP, chart URLs are public).
- **SearXNG:** No auth (self-hosted instance).

## Requirements

- Scrapling skill installed with venv at `~/.openclaw/workspace/skills/scrapling/`
- `npx agent-browser` available (agent-browser 0.26+)
- Remote Chrome with `--remote-debugging-port` at CDP host
- SearXNG instance at `http://<searxng-host>:8081`

## Troubleshooting

### Scrapling returns empty results or 503
Amazon may occasionally block. Wait a few seconds and retry. If persistent, escalate to DynamicFetcher (see scrapling skill). Do NOT escalate to StealthyFetcher unless DynamicFetcher also fails — it's 26x slower with no data advantage.

### CDP connection fails with 404
The WebSocket UUID changes on Chrome restart. Always fetch fresh from `/json/version`. Never hardcode the UUID.

### Reviews page redirects to sign-in
User needs to complete sign-in on the remote Chrome. Check for pending verification at `/ap/cvf/verify`. New tabs opened via browser-level CDP inherit cookies from the same browser profile.

### camelcamelcamel shows "no data"
Product may be too new for price tracking. Check `Last update scan` — if stale, data may be outdated. The current Amazon price may differ from what Camelcamel shows.

### agent-browser session leaked
If a previous session wasn't closed, run `npx agent-browser close` before starting new work.
