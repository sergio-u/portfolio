---
name: hotel-watch
description: >
  Poll hotel booking sites via CDP browser for availability, room types, bed
  configuration, and rate changes on fixed dates. Use when the user wants to
  track lodging for a specific trip, get alerted when rooms open or prices drop,
  or extract full room lists from chain booking engines (Hilton, Marriott).
  Handles slow SPAs and multi-property comparison.
---

# Hotel Watch

Extract reliable room-level availability from chain booking engines, and poll it
on a schedule to detect changes.

Built because aggregators (Google Travel, Kayak, Hotels.com) silently drop date
parameters and fall back to defaults, and keyless scraper tools mix per-night
with total pricing on peak-demand dates. Chain booking engines accessed directly
are the only source that proved trustworthy.

## When to use this

- Tracking a specific trip with fixed dates and a known set of candidate hotels
- Need **bed configuration** (2-queen vs 1-king), not just price
- Peak-demand dates where aggregator pricing is unreliable
- Want alerts on availability appearing, selling out, or price movement

## When NOT to use this

- Casual "what's a good hotel in X" browsing — use `web_search`
- Ordinary travel dates with slack — aggregators are fine and faster
- More than ~10 properties — each poll takes ~60s, this doesn't scale wide

---

## Part 1: Extraction method

### Prerequisites

CDP browser endpoint. See `TOOLS.md` for the current address; it has been
`<home-server>:9222` (remote Chrome). Verify before use:

```bash
curl -s --max-time 15 http://<CDP_HOST>/json/version | jq -r '.webSocketDebuggerUrl'
```

### Rule 1: Target the specific page, never the active tab

`agent-browser snapshot` without a page-specific websocket hits whatever tab is
focused. This silently returns the wrong page and looks like a site failure.

Open a new tab and capture its own websocket:

```bash
# URL must be percent-encoded
T=$(curl -s --max-time 20 -X PUT "http://<CDP_HOST>/json/new?<ENCODED_URL>" \
    | jq -r '.webSocketDebuggerUrl')
npx -y agent-browser --cdp "$T" snapshot
```

Or find an existing tab by URL fragment:

```bash
T=$(curl -s http://<CDP_HOST>/json/list | jq -r \
    '.[] | select(.type=="page") | select(.url|contains("hilton.com/en/search")) | .webSocketDebuggerUrl')
```

### Rule 2: Wait 45-60 seconds for booking SPAs

Chain booking engines render results via XHR after initial page load. At 25-30s
you get `"Finding hotels..."` plus empty placeholder list items. That is **not**
a bot wall — it is an impatient snapshot. Do not conclude the site blocked you.

Verify the page finished: look for a `"N rooms found"` or property-card text
before trusting the result.

### Rule 3: Never truncate the room list

Properties commonly have 11-12 room types. `head -20` on a snapshot cuts the
list mid-way and hides room configurations below the fold.

This caused a real wrong conclusion: "no 2-queen rooms exist at any property"
when 2-queen rooms existed at two of them, listed below the cutoff.

Grep for room markers and allow generous output:

```bash
npx -y agent-browser --cdp "$T" snapshot 2>&1 \
  | grep -iE "rooms found|sold out|Book From|heading \"" | head -60
```

### Rule 4: Extract property codes from the page, never guess

Chain property codes do not follow a guessable pattern. Inferred codes produce
error pages or silently wrong properties.

Pull them from a search-results page:

```bash
npx -y agent-browser --cdp "$T" eval \
  "Array.from(document.querySelectorAll('a')).map(a=>a.href).filter(h=>h.includes('ctyhocn')).join('\n')"
```

Adapt the filter per chain (`ctyhocn` for Hilton, `propertyCode` for Marriott).

---

## Part 2: URL patterns

### Hilton

Per-property room list (the useful one — shows bed config and per-room rates):

```
https://www.hilton.com/en/book/reservation/rooms/?ctyhocn=<CODE>&arrivalDate=<YYYY-MM-DD>&departureDate=<YYYY-MM-DD>&room1NumAdults=<N>&displayCurrency=USD
```

Area search sorted by distance (use to discover properties + sold-out status):

```
https://www.hilton.com/en/search/?query=<CITY%2C%20STATE%2C%20USA>&arrivalDate=<YYYY-MM-DD>&departureDate=<YYYY-MM-DD>&numRooms=1&numAdults=<N>&sortBy=DISTANCE
```

The area search shows `Sold Out` badges and distance in miles per property.
The per-property page shows `"N rooms found. M are currently sold out."`

### Marriott

```
https://www.marriott.com/search/findHotels.mi?propertyCode=<CODE>&fromDate=<MM/DD/YYYY>&toDate=<MM/DD/YYYY>&numberOfRooms=1&numberOfAdults=<N>&lengthOfStay=<N>&isHwsGroupSearch=true&view=list
```

### Expedia (cross-property list view)

Useful as a market baseline and for non-chain properties. The nightly price
filter's minimum value reveals the market floor for those dates.

```
https://www.expedia.com/Hotel-Search?destination=<CITY>&regionId=<ID>&d1=<YYYY-MM-DD>&startDate=<YYYY-MM-DD>&d2=<YYYY-MM-DD>&endDate=<YYYY-MM-DD>&adults=<N>&rooms=1&sort=RECOMMENDED
```

Ask the user to grab `regionId` from a browser search — it is not guessable.

---

## Part 3: What to extract

Per property, per poll:

| Field | Source text |
|---|---|
| rooms available | `"N rooms found"` |
| rooms sold out | `"M are currently sold out"` |
| room type name | `heading "..."` — contains bed config |
| rate | `"Book From $X"` (average per night) |
| property sold out | `Sold Out` badge on area search |
| distance | `"N.NN miles"` on area search |

**Bed configuration lives in the room name.** Parse for:
- `1 King` / `2 Queen` / `2Qn` / `2Q` / `2 King` / `2Kg`
- `Sofabed` — a king+sofabed sleeps 4 but is not two real beds
- `2 Bedroom` / `2bdrm` — separate sleeping areas
- Ignore `Mobility/hearing Access` variants unless needed; they duplicate rates

Note whether the rate shown is **per night** or **total** — chain pages usually
say "We're showing the average price per night." Record which.

---

## Part 4: Checker design

### Storage

One JSON file per watch, under the workspace:

```
memory/watches/<slug>.json
```

```json
{
  "slug": "coachella-2027-w2",
  "dates": {"checkin": "2027-04-15", "checkout": "2027-04-19"},
  "occupancy": {"adults": 4, "rooms": 2},
  "properties": [
    {"chain": "hilton", "code": "LAXIDHX", "name": "Hampton Inn & Suites Indio", "tags": ["shuttle-stop"]}
  ],
  "alert_rules": {...},
  "history": [
    {"ts": "2026-08-19T20:00:00-07:00", "code": "LAXIDHX",
     "available": 3, "sold_out": 10,
     "rooms": [{"name": "1 King Hear Acc Sofabed", "rate": 1053}]}
  ]
}
```

Keep history so alerts fire on **deltas**, not on state. Re-alerting the same
condition daily trains the user to ignore it.

### Alert conditions

Fire when, compared to the previous poll:

- a room matching a **desired bed config** appears where there was none
- a property flips **sold out -> available**
- **rate drops** below a user-set threshold, or by more than N%
- **available count drops** at a preferred property (urgency, not opportunity —
  label it differently)

Stay silent when nothing changed. Silence is the default output.

### Scheduling

Use `cron` with an isolated agentTurn and Telegram announce delivery. Daily is
usually right; go to twice-daily only near a known release date.

Budget ~60s per property. Ten properties is ~10 minutes — fine for a background
isolated run, too slow for an interactive turn.

### Failure handling

If a property page fails to render, record `null` for that poll rather than
writing a zero. A missing datapoint must never look like "sold out" — that
would fire a false urgency alert.

Alert the user if the **same property fails 3 polls in a row**; that usually
means a URL or property code changed.

---

## Known-bad approaches

Do not spend time on these; all were tested and failed:

- **Google Travel / Kayak / Hotels.com deep links** — silently reset dates and
  occupancy to defaults, or 429. The page loads and looks fine while showing
  data for entirely different dates.
- **Plain `curl` against chain sites** — 403.
- **`trvl`** (keyless Go travel CLI) — works for ordinary dates, but on
  peak-demand dates mixes per-night and multi-night-total values in the same
  output column, and its brand filter drops valid properties. Installed at
  `skills/trvl/bin/trvl` if needed for non-peak use.
- **Guessing chain property codes** — every guess was wrong.

## Cross-checking

Before acting on any rate, corroborate across two sources — chain direct plus
Expedia. Where they agreed, the numbers were sound; where a tool disagreed with
both, the tool was wrong.
