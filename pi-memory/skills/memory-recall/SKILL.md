---
name: memory-recall
description: |
  Search the user's pi-memory vault and broader Obsidian knowledge base for prior captures, decisions, plans, gotchas, and domain knowledge. Use when the user asks about past decisions, prior notes, earlier sessions, or anything that might already live in their vault — phrases like "what did we decide about X", "do I have notes on Y", "find anything about Z", "did I write up the jj workflow", "search my notes for K". Picks the right mode automatically: grep for exact-phrase / file-path / log-line lookups, semantic vector-search for paraphrased / conceptual queries, hybrid when the user wants both and high confidence. Returns ranked file/path + snippet pairs the user can open directly in Obsidian.
---

# memory-recall

The user has two sources of stored knowledge:

1. **The pi-memory vault on disk** — `<vault>/80_AI/` plus the weekly notes under `<vault>/10_Weekly/`. This is the source of truth, written by `/note` and the memory-note skill.
2. **AnythingLLM** — the same vault content, indexed for semantic search. The user runs a cron that ingests Obsidian → AnythingLLM; pi-memory queries it read-only.

This skill picks the right query path for the question and returns ranked hits.

## When to recall

Use this skill when the user signals a lookup intent. Strong signals:

- "what did we decide about <topic>"
- "did I write notes on <X>"
- "do I have something on <Y>"
- "find anything about <Z>"
- "what was that jj workflow I had"
- "remind me of <thing> I captured"

Weaker signals (still worth a recall, but verify before going deep):

- The user mentions a topic that's likely in the vault before asking a follow-up.
- The user is about to redo something they may have already solved.

**Skip** when the user is asking a fresh question that wouldn't be in their notes (e.g. "how does PostgreSQL's MVCC work" — that's a documentation question, not a vault question).

## Choosing the mode

The query shape tells you which mode wins:

- **Grep** -- exact phrase, file path, or log-line pattern (e.g. `"smol-toml"`, `"AnythingLLM"`). Fast, deterministic, returns `file:line` you can jump to. Default mode unless the query is clearly fuzzy.

- **Semantic** — paraphrased, conceptual, or natural-language questions (e.g. "what did I decide about jj private commits", "how did I handle the empty-array issue"). The user's actual words won't appear verbatim in the notes; embedding similarity finds the chunk anyway.

- **Hybrid** — when you want both lenses. Useful for ambiguous queries or when the user said "search everything for X". Semantic hits come first, grep hits second.

If the user explicitly passes `--grep`, `--semantic`, or `--hybrid` to `/recall`, honor that. Otherwise pick using the query's shape.

## Workflow

### Step 1 — Pick the mode

Inspect the query. If it contains quoted phrases, file extensions, or distinctly grep-friendly tokens, use `grep`. If it's a question or paraphrase, use `semantic`. If both, use `hybrid`. When unsure, default to whatever `[anythingllm].default_mode` says in config.

### Step 2 — Call memory_search

```
memory_search(query=<the user's query, cleaned of trigger words>, mode=<grep|semantic|hybrid>, limit=8)
```

Limit of 8 is usually right. Larger limits (20+) for "find everything about X" sweeps; 3-4 when the user wants the top hit.

If semantic mode errors (AnythingLLM unreachable, host not set), the tool returns `isError: false` but includes a warning in `details.warnings`. Surface that to the user transparently -- they probably need to start AnythingLLM or set `[anythingllm].host` / `ANYTHINGLLM_HOST`.

### Step 3 — Read the candidate(s)

For grep hits you already have the file + line. For semantic hits you have `chunkSource` (an `obsidian://<vault>/<path>` URL) and a snippet but not the full file. If a hit looks like the answer, read the actual file to confirm before reporting. (Semantic search returns the chunk that matched; the surrounding context often has the real answer.)

### Step 4 — Format the response

Lead with the top hit's content (the part that answers the user's question), not just the file path. Then list the other candidates with file paths so the user can jump in Obsidian.

Good response shape:

```
From <file or chunkSource>: "<short quote that answers the question>"

Other hits:
- <path1> — <snippet1>
- <path2> — <snippet2>
```

If no hits matched, say so directly. Don't pretend to have an answer. Suggest alternative search terms when reasonable.

## Examples

**Example 1 — exact phrase**

User: "find my notes on smol-toml"

Mode: `grep` (exact token, file-system friendly).
Action: `memory_search(query="smol-toml", mode="grep", limit=8)`.

If 2 hits return, surface them with file:line and snippets.

**Example 2 — paraphrased question**

User: "what did I decide about jj's private commit revset?"

Mode: `semantic`. The exact phrase "private commit revset" may not appear; embedding search finds the relevant chunk.
Action: `memory_search(query="jj private commit revset decision", mode="semantic", limit=5)`.

After retrieval, read the top chunk's source file and surface the decision verbatim.

**Example 3 — vault sweep**

User: "search everything for AnythingLLM"

Mode: `hybrid`. The user wants both exact matches and conceptual mentions.
Action: `memory_search(query="AnythingLLM", mode="hybrid", limit=20)`.

Report counts (`5 grep matches, 8 semantic matches`) and a few top hits from each.

**Example 4 — AnythingLLM down**

User: "what did I decide about X" — semantic search would be right, but AnythingLLM is unreachable.
Action: `memory_search(query="X decision", mode="hybrid", limit=10)`.

The tool returns warnings about semantic failure but grep hits land. Surface the grep hits and tell the user: "AnythingLLM was unreachable; showing local grep results only. Check `[anythingllm].host` or `ANYTHINGLLM_HOST` if you need semantic too."

## What this skill MUST NOT do

- Don't fabricate content. If the answer isn't in a returned snippet, say "no matching notes found" rather than guess.
- Don't write to the vault from this skill — `memory-recall` is read-only. Capture is `memory-note`'s job.
- Don't paste massive chunks into the response; quote one or two sentences max and link to the file path. The user opens Obsidian for the full context.
- Don't run all three modes when one suffices. Hybrid costs both a vector-search round-trip and a local grep; only use it when the query genuinely needs both.
- Don't mix in unrelated `/recall` queries from earlier in the session — each invocation is a fresh search.
