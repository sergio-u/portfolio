---
name: packing-list
description: >
  Build trip-specific packing lists with Reddit research, weather forecasts, and
  Todoist integration. Use when the user says "pack for", "packing list",
  "what to bring", "what should I pack", "trip checklist", or is planning
  travel and needs to figure out what to take. Covers festivals, vacations,
  business trips, camping, international travel, and any multi-day trip.
---

# Packing List

Build a researched, quantified packing list for any trip and push it to Todoist.

## Execution

### Step 1: Gather trip parameters

Extract from the user's request (ask only for what's missing):

- **Destination** and **type** (festival, beach, business, hiking, city, etc.)
- **Dates** (departure → return) — needed for night count and weather
- **Accommodation** (camping, hotel, Airbnb, hostel) — affects gear needs
- **Transport** (flying carry-on only, checked bag, driving) — affects volume constraints
- **Special needs** mentioned (work gear, formal events, activities)

### Step 2: Research (parallel)

Run these in parallel:

1. **Weather forecast** for destination dates — use the weather skill. Include daily highs, lows, wind, precipitation. This drives fabric and layering decisions.
2. **Reddit/community research** — search `site:reddit.com <destination> packing list` and `site:reddit.com <destination> what to bring tips`. Fetch the top 2-3 threads. Extract consensus recommendations and frequently mentioned non-obvious items.
3. **Existing notes** — check if the user has a relevant Obsidian note (survival guide, travel guide) via `rg -l -i "<destination>" ~/Documents/Sync/Notebook/2026-H1/ 2>/dev/null`. Read if found.

### Step 3: Build the list

#### Structure

Organize into categories. Standard categories (skip any that don't apply):

- **Clothing** — with specific quantities based on trip length and laundry access
- **Sun / Weather Protection**
- **Health & Safety**
- **Electronics & Charging**
- **Toiletries & Recovery**
- **Day Bag Essentials** (what you carry daily)
- **Gear** (camping, hiking, sport-specific)
- **Work Stuff** (if applicable)
- **Documents & Money**
- **Food & Hydration** (if self-catering or remote)

#### Detail level

Follow these conventions for every item:

- **Explicit quantities** for anything you need multiples of: `T-shirts x5`, not `T-shirts`
- **Fabric/material notes** when it matters: `Lightweight pants x2 (linen or synthetic joggers)`, not just `Pants x2`
- **Parenthetical rationale** for non-obvious items: `KN95 masks x3 (dust storms common)`
- **Skip generic items** the user obviously owns and will bring (wallet, phone, keys) unless the trip type makes them worth calling out (e.g., passport for international)
- Quantity formula: **days** (not nights+1) for daily-wear items (shirts, underwear, socks). Count travel days that need a fresh outfit. Don't overcount — user will push back.
- **Include a [Pre-departure] section** with chores like cleanup, trash, dishes — these get forgotten and are satisfying to check off

#### Clothing decision framework

Based on weather and trip type, recommend specific fabric types:

| Condition | Recommend | Avoid |
|---|---|---|
| Hot + dry (desert, festival) | Rayon/viscose shirts + nylon/polyester shorts/pants | Denim, heavy cotton, pure polyester shirts |
| Hot + humid (tropical) | Moisture-wicking synthetics, linen | Cotton (holds moisture) |
| Cold | Merino wool layers, down | Cotton base layers |
| Mixed/variable | Layering system (base + mid + shell) | Single heavy layer |
| Formal needed | Wrinkle-resistant blends, merino | Linen (wrinkles badly) |
| Dusty/dirty | Synthetics (shake clean, quick-dry) | Light colors, delicate fabrics |

Fabric notes (for when the user asks):
- **Rayon = viscose** (US vs European label name, same fabric). Modal and lyocell/Tencel are premium variants.
- **Nylon = polyamide** (same thing, different label convention)
- **Polyester** is fine for bottoms but avoid for shirts in heat (traps heat, clammy)
- **Linen** breathes great but wrinkles immediately and shows sweat stains
- **Poly-rayon blends** are the sweet spot for pants (breathable + durable + quick-dry)

### Step 4: Present for review

Show the full list organized by category before creating tasks. Keep it scannable — bullet list, not paragraphs. Ask if anything should be added, removed, or adjusted.

### Step 5: Create in Todoist

Use the todoist skill. Structure:

- One **single parent task** for the whole trip (e.g., "Coachella Packing List")
- All items as **flat subtasks** underneath, prefixed with category tag: `[Clothing]`, `[Sun]`, `[Health]`, etc.
- No nested category parents — a single flat list is easier to scan and check off in Todoist
- Label all tasks with `AI` + a trip-specific label (e.g., `coachella`, `japan-trip`)
- Place in `Personal > Inbox` unless user specifies otherwise
- Set parent due date to departure date so it shows as actionable

#### Pre-trip grocery/shopping run (optional)

If the list includes items the user likely needs to buy (supplements, specific gear, specialty items), offer to create a separate "Pre-trip shopping" parent task with those items called out. Distinguish between "buy at home" (cheaper, specialty) vs "buy at destination" (perishables, ice, basics).

### Step 6: Offer follow-ups

After creating the list, offer:

- "Want me to save a packing guide to your Obsidian vault for this destination?"
- "Want me to add a pre-trip shopping run task?"
- "Anything else to add or adjust?"

## Conventions

- Always research before building — don't rely on generic knowledge alone. Community wisdom surfaces non-obvious essentials.
- Weather drives everything — fabric choices, layering, quantities of sun/rain protection.
- Quantities > vague items. Every multi-item entry gets a count.
- **Don't overcount.** Use actual trip days, not nights+1. The user will catch inflated counts — better to be slightly lean (they can always rewear) than to suggest overpacking.
- Parenthetical rationale for non-obvious items — the user should understand *why* without asking.
- When in doubt about an item, include it with a note rather than omitting it.
- Match the user's detail preferences: Sergio prefers specific quantities, fabric recommendations, and buy-location advice. Adjust granularity to match how the user engages.
- **Expect iteration.** The first draft will get adjusted — user will add personal items (bandanas, specific coffee, etc.), adjust quantities, and swap out items. Build the list to be easy to modify.
- **Supplements should match the trip context.** Ask about alcohol/substance use to tailor recovery items — don't default to hangover kits if they won't drink much.

## Requirements

- Weather skill (for forecasts)
- Todoist skill (for task creation)
- Web search (for Reddit/community research)
- Obsidian vault access (optional, for existing destination notes)
