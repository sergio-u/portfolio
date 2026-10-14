---
name: market-value
description: >
  Research the current resale/market value of any product using eBay sold listings,
  HifiShark, and other secondary market data. Compute price statistics, all-in cost
  estimates (tax, shipping, import duties), and buy/pass recommendations based on the
  user's risk tolerance. Use when the user asks "what's this worth", "market value",
  "resale value", "how much should I pay", "is this a good deal", "price check",
  "should I buy this", "what are these selling for", "eBay comps", "sold prices",
  or wants to evaluate a purchase against recent comparable sales.
---

# Market Value

## Workflow

### 1. Gather Comparable Sales

Search eBay sold/completed listings for the exact product. Filter out accessories, parts, and bundles.

```
# Primary: eBay sold listings (US-located, used condition)
web_fetch https://www.ebay.com/sch/i.html?_nkw=%22PRODUCT+NAME%22&LH_Sold=1&LH_Complete=1&LH_ItemCondition=3000

# With noise filtering (exclude common accessory keywords)
web_fetch https://www.ebay.com/sch/i.html?_nkw=%22PRODUCT+NAME%22+-cable+-case+-tips+-replacement+-part&LH_Sold=1&LH_Complete=1&LH_ItemCondition=3000
```

**eBay URL parameters:**
- `LH_Sold=1&LH_Complete=1` — sold/completed only
- `LH_ItemCondition=3000` — used condition
- `LH_ItemCondition=1000` — new condition
- `LH_LocatedIn=1` — US-located sellers only
- `_udhi=MAXPRICE` — max price filter
- `_udlo=MINPRICE` — min price filter

**Supplemental sources** (use when eBay data is thin):
- **HifiShark** (audio gear): `web_fetch https://www.hifishark.com/search?q=PRODUCT`
- **Reverb** (music gear): `web_fetch https://reverb.com/marketplace?query=PRODUCT&show_only_sold=true`
- **StockX** (sneakers/streetwear): `web_fetch https://stockx.com/search?s=PRODUCT`
- **Swappa** (phones/laptops): `web_fetch https://swappa.com/search?q=PRODUCT`
- **Reddit price checks**: `web_search "PRODUCT price check site:reddit.com"`

### 2. Extract and Clean Prices

From the fetched results, extract sold prices. For each listing note:
- Sale price
- Shipping cost (or "free")
- Location (US vs international)
- Sale type: auction, BIN, or "best offer accepted"
- Seller feedback score (flag 0% or <10 feedback)

**Discard:**
- Listings that are clearly different items (bundles, wrong model, parts-only)
- Outliers >2 standard deviations from median (unless sample is tiny)
- "Best offer" listings where accepted price is unknown (use as upper bound only)

### 3. Analyze with Script

Run the analysis script for statistics + recommendation:

```bash
python3 skills/market-value/scripts/analyze_prices.py \
  --prices '900,950,1059,1100,1300' \
  --candidate 950 \
  --tax 0.1025 \
  --shipping 30 \
  --max-loss 80
```

**Parameters:**
- `--prices` — comma-separated comparable sold prices
- `--candidate` — the listing price being evaluated
- `--tax` — state sales tax rate (WA = 0.1025 for Seattle)
- `--shipping` — shipping cost for the candidate listing
- `--broker-fee` — customs broker/handling fee if international
- `--max-loss` — user's max acceptable loss if they resell
- `--resale-fee` — platform fee percentage for resale (default 0.13 = eBay 13%)

**Output includes:**
- Price statistics (min, max, median, P25, P75, stdev)
- Market range (low/mid/high)
- All-in cost calculation
- Verdict: GREAT_BUY / GOOD_BUY / MARKET_RATE / OVERPAY / PASS
- Suggested max bid (based on max-loss if provided)

### 4. Check Import Costs (International Listings)

When evaluating international listings, check tariff rates:
- Read `references/tariffs.md` for common categories
- For uncommon items, search USITC: `web_fetch https://hts.usitc.gov/search?query=HTS_CODE`
- Factor into all-in: duty + tax + shipping + broker fee

**Key rules:**
- Most consumer electronics (headphones, laptops, phones) = **duty-free** from non-China origins
- State sales tax applies regardless (eBay collects it)
- eBay GSP listings include import charges upfront but often overcharge 10-20%

### 5. Present Results

Summarize for the user:
- Market range (low / typical / high) from recent comps
- All-in estimate for the candidate listing
- Clear verdict with reasoning
- Suggested offer price if applicable
- Risk factors (seller feedback, international shipping, condition uncertainty)

**Format for Telegram** (no markdown tables):
```
Market range (used, recent):
- Low: $X (P25)
- Typical: $Y (median)
- High: $Z (P75)
- Sample: N sold listings

This listing:
- Price: $A + $B shipping
- Tax (~X%): +$C
- All-in: ~$D

Verdict: [VERDICT] — [reason]
Suggested max offer: $E
```

## Default Assumptions

- **Tax rate:** 10.25% (Seattle, WA) — adjust if user specifies another location
- **Resale platform fee:** 13% (eBay) — adjust for other platforms (Reverb ~8%, r/AVexchange ~0%, StockX ~10%)
- **Condition:** Used/pre-owned unless specified
- **Market:** US domestic preferred; international comps noted separately
