# open-claw-workspace

Workspace for CLAW, the personal assistant I ran on
[OpenClaw](https://github.com/openclaw/openclaw) from March to August 2026,
before moving to Hermes (see [hermes-personal](../hermes-personal/)). OpenClaw
loads this folder as the agent's home. Persona and operating rules live in the
top-level Markdown files, and each capability is a self-contained skill under
`skills/`.

## Highlights

- Memory curation with rollback. OpenClaw's Dreaming pass promotes session notes
  into long-term memory. [`scripts/memory_curator.py`](scripts/memory_curator.py)
  wraps each promotion run in a lock, snapshots, validation, and an idempotency
  ledger. The agent edits `MEMORY.md` and `USER.md` and records its decisions;
  the script validates them, rejects chat metadata leaking into memory, and
  commits or rolls back. [`scripts/slice.py`](scripts/slice.py) and
  [`scripts/check_review.py`](scripts/check_review.py) curate old raw transcripts
  one small slice at a time. Tests are in
  [`scripts/test_memory_curator.py`](scripts/test_memory_curator.py).
- Measured scraping choices. The `amazon` skill picks its fetcher from an
  [experiment](skills/amazon/references/experiment-results.md) that compared
  eight tools on search and product pages. Plain Scrapling HTTP returned the
  same search data as a headless browser 26 times faster.
- Skills that combine sources. `festival-planner` builds a daily set schedule
  from my Tidal library, friends' plans, and venue maps. `hotel-watch` polls
  booking sites through a browser and reports when rooms open or prices drop.

## Layout

| Path | Purpose |
| --- | --- |
| `SOUL.md`, `IDENTITY.md` | Persona, tone, and boundaries |
| `AGENTS.md` | Session startup, memory rules, red lines, group-chat etiquette |
| `TOOLS.md` | Setup-specific notes: browser CDP, search, dependency updates |
| `skills/` | 38 skills, each with a `SKILL.md` plus scripts and references |
| `config/` | MCP server config (`mcporter.json`) and memory-curation prompts |
| `scripts/` | Memory curation tooling and its tests |

## Skills

| Area | Skills |
| --- | --- |
| Notes and knowledge | obsidian, digest-day, digest-this, knowledge-base, instapaper, pdf-analyzer |
| Tasks and work | todoist, gws |
| Research and web | hackernews, reddit, gh, scrapling, trafilatura, youtube-transcript, annas-archive |
| Shopping and money | amazon, market-value, splitwise |
| Travel and food | flights, hotel-watch, travel-gpx, packing-list, restaurant-finder, michelin-guide, meal-planner, mealie |
| Music and film | tidal, spotify, festival-planner, letterboxd |
| Home | homeassistant |
| Workspace upkeep | align-workspace, my-skills, new-skill, mcp-skill-creator, upgrade-check |

`ponytail` and `last30days-official` are third-party skills installed from
ClawHub (see `.clawhub/lock.json`).

## Not included

Personal state is removed: `USER.md`, `MEMORY.md`, `HEARTBEAT.md`, `DREAMS.md`,
`memory/`, notes, and machine setup scripts. Skills that mention those files
expect them in a live workspace. Two work-specific skills, for Azure DevOps and
sprint syncing, are also left out.

Credentials come from environment variables such as `TODOIST_API_KEY` and
`ANYTHINGLLM_API_KEY`. Private hosts appear as placeholders such as
`<home-server>` and `<searxng-host>`, and work project names are generic
(`ProjectA`, `Contoso.Core`).
