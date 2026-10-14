# Multi-Agent Skill Design Workflow

Guide for designing skills that use parallel subagent orchestration. Based on the digest-day skill pattern (Apr 2026).

## When to Use This Pattern

Use parallel subagents when:
- The task processes multiple independent units (days, files, repos, sources)
- Each unit fits comfortably in one agent's context but all units together would be too large
- First-pass synthesis can be done independently; aggregation needs the full picture
- Wall-clock time matters -- parallel is faster than sequential

Do NOT use subagents when:
- The task is small enough for one agent (1-2 units, light data)
- Units are interdependent (each needs results from the previous)
- The main value is in aggregation, not per-unit synthesis

## Design Process

### 1. Identify the parallelizable unit

What is the independent chunk of work? Examples:
- One day's session transcripts (digest-day)
- One repository's issues (code review)
- One data source's results (research aggregation)

Each unit should be processable without knowledge of other units.

### 2. Choose the data handoff method

**File-based (recommended for large data):**
- Extract data to `/tmp/<skill>-<unit-id>.json`
- Subagent reads the file via `read` tool
- Works for any data size up to the model's context window

**Task-string (for small data only):**
- Embed the data directly in the `task` parameter
- Limit: ~2-3KB of data before the task string gets unwieldy
- Fine for metadata, IDs, short summaries

### 3. Design the subagent prompt

Create a prompt template in `references/subagent-prompt.md` with placeholders:

```markdown
# Subagent Prompt Template

Replace `{{UNIT_ID}}`, `{{FILE_PATH}}`, etc. with actual values.

---

You are a [role]. Read the file {{FILE_PATH}} which contains [description].

[Filtering rules -- be specific and give examples of what to skip/keep]

[Classification rules if applicable]

[Output format -- be exact, subagents follow format instructions well]
```

**Prompt design tips:**
- Be explicit about what to skip -- subagents (especially smaller models) err on inclusion
- Give concrete examples of noise vs signal for your domain
- Specify the exact output format -- subagents can't improvise structure well
- Include "if nothing worth reporting, say X" to handle empty results gracefully
- Keep the prompt under ~500 words; longer prompts dilute the filtering instructions

### 4. Choose the named subagent tier

Test at least two named agents before committing. Run the same unit through each and compare:

| Factor | `small` / Flash-fast agents | `medium` / Sonnet-mid agents | `large` / Opus-large agents |
|---|---|---|---|
| Speed | ~3s | ~15-25s | ~30-60s |
| Filtering quality | Poor -- lists everything | Good -- applies judgment | Best -- nuanced |
| Cost | Lowest | Moderate | Highest |
| When to use | Extraction only, no judgment needed | Synthesis with filtering (sweet spot) | Complex reasoning, ambiguous classification |

**General guidance:** Start with the cheapest named agent (`small`), test it, move up only if quality is insufficient. For most synthesis-with-filtering tasks, `medium` (Sonnet-class) hits the sweet spot.

### 5. Wire the orchestration in SKILL.md

Document these steps in your skill's Execution section:

```
Step 1: Extract/prepare data
Step 2: Save per-unit files (if file-based handoff)
Step 3: Spawn subagents (parallel)
Step 4: Aggregate results (after all complete)
Step 5: Curate/edit (main agent quality pass)
Step 6: Present for review
Step 7: Execute (write files, update systems, etc.)
```

### 6. Handle the orchestration mechanics

**Spawning:**
```
sessions_spawn:
  mode: run
  agentId: <small|medium|large>
  lightContext: true       # skip workspace files, keep it fast
  label: <skill>-<unit-id> # for tracking
  task: <prompt with substituted placeholders>
```

**Waiting:**
After spawning all subagents, call `sessions_yield`. Completions arrive as push events -- no polling needed.

**Tracking:**
Keep a mental list of expected completions. Only proceed to aggregation after ALL have returned. If a subagent fails, note it and either retry or skip that unit.

### 7. Design the aggregation pass

The main agent's job after subagents return:
- **Quality control:** Trim over-detailed results, cut noise that slipped through
- **Cross-unit synthesis:** Detect patterns, threads, or themes that span units
- **Deduplication:** Same topic appearing in multiple units -- keep the best version
- **Gap detection:** Check if any unit's results seem suspiciously empty given the input size

## Skill Structure

```
skills/<name>/
  SKILL.md                          # Main skill with orchestration steps
  references/
    subagent-prompt.md              # Prompt template for subagents
  scripts/
    extract.py (or similar)         # Data extraction/preparation
```

## Testing Checklist

Before finalizing a multi-agent skill:

- [ ] Test subagent prompt on 1 easy unit and 1 hard unit
- [ ] Compare at least 2 named-agent tiers (e.g., `small` vs `medium`)
- [ ] Verify parallel spawn works (spawn 2-3 simultaneously)
- [ ] Confirm file-based handoff works for your largest expected unit
- [ ] Test the aggregation pass -- does the main agent add value beyond concatenation?
- [ ] Test the empty case -- what happens when a unit has nothing worth reporting?
- [ ] Verify the full end-to-end flow once before documenting

## Anti-Patterns

- **Subagent for everything:** Don't spawn subagents for work that fits in one context window. The overhead isn't worth it for small tasks.
- **No curation pass:** Subagent output should never go directly to the user without main agent review. Subagents are workers, not editors.
- **Polling loops:** Don't poll for subagent completion. Use `sessions_yield` and wait for push events.
- **Shared state between subagents:** Each subagent is isolated. If unit B depends on unit A's output, they can't be parallel.
- **Giant prompts:** Keep subagent prompts focused. A 1000-word prompt with 20 rules means the subagent follows none of them well.
- **Skipping model testing:** Always test -- model capabilities vary significantly for synthesis tasks.
