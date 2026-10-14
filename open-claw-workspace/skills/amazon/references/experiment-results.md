# Amazon Scraping Experiment Results
**Date:** 2026-04-17 | **Query:** "reading stand" | **Target ASIN:** B0C3TSQ4VQ

---

## Phase 1: Discovery (Search Results)

| Tool | Time | Results | Price | Rating | ASIN | Images | Review Count | Blocked? |
|------|------|---------|-------|--------|------|--------|--------------|----------|
| **SearXNG** | 666ms | 31 | No | No | No | URLs only | No | No |
| **Scrapling Fetcher** | 1,276ms | 60 | Yes | Yes | Yes | Thumb URLs | No | No |
| **Scrapling DynamicFetcher** | 33,382ms | 60 | Yes | Yes | Yes | Thumb URLs | No | No |
| **Scrapling StealthyFetcher** | — | — | — | — | — | — | — | Not tested (too slow for search) |
| **web_fetch** | — | — | — | — | — | — | — | **503 blocked** |
| **trafilatura** | 3,195ms | Garbage | No | No | No | No | No | Extracted wrong content |
| **raw curl** | 138ms | 0 | No | No | No | No | No | **503 blocked** |
| **agent-browser CDP** | 5,913ms | 834 lines | Yes | Yes | via refs | via refs | Yes | No |

### Discovery Winner: **Scrapling Fetcher**
- 26x faster than DynamicFetcher with identical data
- Gets structured fields (title, price, rating, ASIN, thumbnail URL)
- Plain HTTP with TLS spoofing is enough — Amazon doesn't block search pages aggressively
- **Runner-up:** SearXNG for URL-only discovery (0.6s, zero risk of blocks, but no structured product data)

---

## Phase 2: Product Detail Page

| Tool | Time | Title | Price | Rating | Reviews# | Bullets | Images | Brand | Avail | Hi-Res Imgs |
|------|------|-------|-------|--------|----------|---------|--------|-------|-------|-------------|
| **Scrapling Fetcher** | 2,527ms | Yes | Yes | Yes | Yes (2,314) | 5 full bullets | 7 thumbs + main | Yes | Yes | Yes (via JS regex) |
| **Scrapling StealthyFetcher** | 34,242ms | Yes | Yes | Yes | Yes (2,314) | 5 full bullets | 5 thumbs + main | Yes | Yes | No advantage |
| **Scrapling DynamicFetcher** | ~33s (est) | Same as Fetcher | — | — | — | — | — | — | — | — |
| **trafilatura** | 2,695ms | Garbage (GRS cert text) | No | No | No | No | No | No | No | No |
| **web_fetch** | — | — | — | — | — | — | — | — | — | **503 blocked** |
| **agent-browser CDP** | 4,432ms (open) + 10,453ms (snapshot) | Yes | Yes ($29.99) | Yes (4.7/5) | Yes | Via tree | 8+ customer img buttons | Yes | Yes | No (needs click) |

### Product Detail Winner: **Scrapling Fetcher**
- **13.5x faster** than StealthyFetcher with identical output
- Returns structured CSS-selectable data: title, price, rating, review count, feature bullets, brand, availability
- **Bonus: Hi-res image extraction** via regex on inline `<script>` tags (6 images at 1500px) — cheaper than any browser approach
- **Agent-browser** provides richer contextual data (button states, interactive refs, customer image buttons) but at 15s total is 6x slower for less structured data

---

## Phase 3: Reviews

| Tool | Time | Reviews | Titles | Ratings | Bodies | Verified | Dates | Auth Required? |
|------|------|---------|--------|---------|--------|----------|-------|----------------|
| **Scrapling Fetcher (product page)** | 2,084ms | 10 | Yes | Partial (6/10) | Yes (300ch) | Yes | No | **No** |
| **Scrapling Fetcher (reviews URL)** | 927ms | 0 | — | — | — | — | — | **Yes - redirected to sign-in** |
| **Scrapling DynamicFetcher (reviews URL)** | 2,640ms | 0 | — | — | — | — | — | **Yes - redirected to sign-in** |
| **trafilatura (reviews URL)** | 885ms | 0 | — | — | — | — | — | **Yes - sign-in page** |
| **agent-browser CDP (product page)** | ~15s | 6+ | Yes | Yes | Truncated | Yes | **Yes** | **No** |
| **SearXNG (external reviews)** | 596ms | External links | YouTube review, Amazon.ca, Wirecutter | N/A | Snippets | N/A | N/A | **No** |

### Reviews Winner: **Scrapling Fetcher on product page** (+ SearXNG for external)
- **Key finding: Dedicated reviews pages require Amazon login. Product pages embed ~10 top reviews for free.**
- Fetcher gets 10 reviews in 2s with title, body (300ch), verified badge, and partial ratings
- Agent-browser gets reviews with full dates but takes 7x longer and data is less structured
- SearXNG can find external review sources (YouTube, blogs) as a complement

---

## Phase 4: Image Analysis

| Approach | Time | Quality | Buyer-Useful Info |
|----------|------|---------|-------------------|
| **Scrapling hi-res URL extraction** | ~2s (bundled with product fetch) | 1500px originals | URLs only — need vision model |
| **curl download + vision model** | ~3s download + ~5s analysis | Full analysis | Material, size cues, adjustability, use cases, quality indicators |
| **agent-browser screenshot** | ~2s | Full page render | Page layout, visual hierarchy, but not product detail |

### Image Analysis Winner: **Scrapling URLs → curl download → vision model**
- Extract hi-res URLs from product page scripts (free with product fetch)
- Download select images via curl (fast, parallel)
- Feed to vision model for material/quality/use-case analysis
- Total pipeline: ~7s for 3 analyzed images

---

## Phase Summary: Recommended Pipeline

```
┌─────────────┐    ┌──────────────────┐    ┌───────────────────┐    ┌──────────────┐
│  DISCOVERY   │    │  PRODUCT DETAIL  │    │     REVIEWS       │    │    IMAGES     │
│              │    │                  │    │                   │    │              │
│  Scrapling   │───▶│  Scrapling       │───▶│  Scrapling        │───▶│  curl +      │
│  Fetcher     │    │  Fetcher         │    │  Fetcher          │    │  vision      │
│  (~1.3s)     │    │  (~2.5s)         │    │  (on product pg)  │    │  model       │
│              │    │  + JS regex for  │    │  (~0s, bundled)   │    │  (~7s)       │
│  60 results  │    │  hi-res images   │    │  10 reviews       │    │  3 images    │
└──────┬───────┘    └──────────────────┘    └───────────────────┘    └──────────────┘
       │
       │ (optional parallel enrichment)
       │
  ┌────▼────────┐
  │  SearXNG    │
  │  (~0.6s)    │
  │  External   │
  │  reviews +  │
  │  URLs       │
  └─────────────┘
```

### Total time for full pipeline: ~13s per product (vs ~50s+ with browser-based approaches)

---

## Tool Verdict

| Tool | Best For | Avoid For | Speed | Reliability |
|------|----------|-----------|-------|-------------|
| **Scrapling Fetcher** | Everything on Amazon (search, product, reviews) | Nothing — it works | ★★★★★ | ★★★★★ |
| **SearXNG** | URL discovery, external reviews, zero-risk recon | Structured product data | ★★★★★ | ★★★★ |
| **Vision model** | Product image analysis, quality assessment | N/A — complementary | ★★★★ | ★★★★★ |
| **Scrapling DynamicFetcher** | Fallback if Fetcher gets blocked | Primary use (26x slower, same data) | ★★ | ★★★★ |
| **Scrapling StealthyFetcher** | Last resort anti-bot bypass | Anything else (34s per page) | ★ | ★★★★ |
| **agent-browser CDP** | Interactive flows (login, pagination, filters) | Data extraction (slow, unstructured) | ★★★ | ★★★ |
| **trafilatura** | Article/blog extraction | Amazon (extracts garbage) | ★★★★ | ★ (for Amazon) |
| **web_fetch / raw curl** | Simple pages | Amazon (503 blocked) | ★★★★★ | ★ (for Amazon) |

---

## CDP Notes
- **Remote Chrome at `<home-server>:9222`** — Chrome 147
- agent-browser needs the full `/devtools/browser/<uuid>` WebSocket URL from `/json/version`
- The UUID changes on Chrome restart, so the skill should always fetch it dynamically
- CDP is the **only** path for interactive flows (clicking through pagination, filters, review expansion)
- For a product comparison skill, CDP is overkill — reserve it for edge cases

---

## Phase 5: Authenticated Access (via CDP)

### Setup
- Remote Chrome at `<home-server>:9222` (Chrome 147)
- User signed in manually in the browser
- agent-browser connects via `ws://<home-server>:9222/devtools/browser/<UUID>`
- UUID from `curl http://<home-server>:9222/json/version | jq .webSocketDebuggerUrl`
- **New tabs opened via browser-level CDP inherit session cookies**

### CDP Connection Notes
- `--cdp "ws://host:9222"` → **fails** (404)
- `--cdp "http://host:9222"` → **fails** (404)
- `--cdp "ws://host:9222/devtools/browser/<UUID>"` → **works** (new tab with shared cookies)
- `--cdp "ws://host:9222/devtools/page/<ID>"` → **works** (attach to existing tab)
- UUID changes on Chrome restart — must always fetch dynamically

### Authenticated Reviews Page

| Feature | Unauthenticated (product page) | Authenticated (reviews page via CDP) |
|---------|-------------------------------|-------------------------------------|
| Reviews per page | 10 (embedded, top reviews) | 10 (dedicated, with pagination) |
| Pagination | No | Yes (`?pageNumber=N` works) |
| Sort options | No | Yes (helpful, recent) |
| Star filtering | No | Yes (1-5 star, positive, critical) |
| Variant filtering | No | Yes (all variants, specific colors) |
| Media filtering | No | Yes (text, image, video) |
| Review titles | Partial (6/10 had titles) | Full (all 10 have titles) |
| Review dates | No | Yes (full date with location) |
| Author names | No | Yes |
| Helpful votes | No | Yes |
| Review images | No | Yes (with thumbnail URLs) |
| Total count | "2,314" (text only) | "946 customer reviews" (filterable) |
| Histogram | Not extractable | Available (via selectors) |

### Cookie Transfer to Scrapling: FAILED
- Exported `document.cookie` (945 bytes, includes `session-token`)
- Passed as `Cookie:` header in Scrapling Fetcher → **still 404 / redirected to sign-in**
- Amazon validates more than cookies (likely TLS fingerprint, referrer chain, or browser headers)
- **Verdict: Authenticated content requires agent-browser CDP. No shortcut.**

### Q&A Section: Not Available
- `/ask/questions/asin/B0C3TSQ4VQ` → 404 (not a valid URL pattern anymore)
- Q&A embedded on product pages was not found via Scrapling selectors either

---

## Revised Pipeline (with auth)

```
┌─────────────┐    ┌──────────────────┐    ┌───────────────────────┐    ┌──────────────┐
│  DISCOVERY   │    │  PRODUCT DETAIL  │    │       REVIEWS         │    │    IMAGES     │
│              │    │                  │    │                       │    │              │
│  Scrapling   │───▶│  Scrapling       │───▶│  IF deep reviews:     │───▶│  curl +      │
│  Fetcher     │    │  Fetcher         │    │  agent-browser CDP    │    │  vision      │
│  (~1.3s)     │    │  (~2.5s)         │    │  (~5s/page, authed)   │    │  model       │
│              │    │  + JS regex for  │    │  - pagination         │    │  (~7s)       │
│  60 results  │    │  hi-res images   │    │  - star filtering     │    │  3 images    │
│              │    │                  │    │  - sort by recent     │    │              │
│              │    │  + 10 embedded   │    │                       │    │              │
│              │    │  reviews (free)  │    │  IF quick overview:   │    │              │
│              │    │                  │    │  use embedded 10      │    │              │
│              │    │                  │    │  from product page    │    │              │
└──────┬───────┘    └──────────────────┘    └───────────────────────┘    └──────────────┘
       │
       │ (optional parallel enrichment)
       │
  ┌────▼────────┐
  │  SearXNG    │
  │  (~0.6s)    │
  │  External   │
  │  reviews +  │
  │  URLs       │
  └─────────────┘
```

---

## Key Findings
1. **Plain HTTP wins for search + product pages.** Scrapling Fetcher handles both without JS rendering.
2. **Embedded reviews (10) are free** on product pages — no auth needed. Good for quick overview.
3. **Dedicated reviews page requires auth** and only works via agent-browser CDP (cookies alone don't transfer to Scrapling).
4. **Auth unlocks**: pagination, star filtering, sort options, review dates, authors, helpful votes, review images.
5. **Hi-res images are in inline scripts** — extractable via regex, no browser interaction needed.
6. **SearXNG is a fast, free complement** for external reviews and URL discovery.
7. **Vision model on product images** adds material/quality analysis impossible from text alone.
8. **DynamicFetcher and StealthyFetcher are 13-26x slower** with zero data advantage on Amazon.
9. **CDP UUID changes on Chrome restart** — skill must always fetch it dynamically from `/json/version`.
10. **agent-browser must use browser-level WebSocket URL**, not bare host:port.
