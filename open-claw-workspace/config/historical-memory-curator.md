# Historical Memory Curation Plan

## Objective

Reduce semantic-search noise from raw historical session summaries without losing recoverability or useful durable knowledge.

## Scope and cadence

- Process only files older than 60 days.
- Work in slices of at most 10 files or 100 KB, whichever comes first.
- Start with obvious raw session summaries; leave curated daily notes untouched.
- Run manually until three slices pass quality and recall checks, then consider a low-frequency scheduled job.

## Storage tiers

1. `USER.md`: explicit stable profile directives and corrections.
2. `MEMORY.md`: compact durable non-profile facts and decisions.
3. `memory/curated/YYYY-MM-DD.md`: concise searchable historical summaries that remain useful but do not belong in bootstrap memory.
4. `state/memory-curator/history-archive/<slice>/`: immutable raw source files plus hashes and an operation manifest; excluded from memory search but recoverable.

## Per-file decisions

- `archive-only`: no unique durable knowledge remains, or the current
  skill/config/docs already own it.
- `summarize`: extract one or more grounded standalone claims into the curated
  summary, then archive the raw source.

If a file seems too valuable to summarize, that is a signal it belongs in a
skill or reference doc instead. Leave it in place and move on rather than
inventing a third category.

## Semantic policy

Exclude sender/session metadata, message IDs, greetings, tool-call narration, routine status updates, transient prices or event logistics, stale troubleshooting, credentials, sensitive values, and assistant recommendations Sergio did not adopt.

Before retaining a claim, check current canonical sources. Prefer the current skill, `TOOLS.md`, config, `USER.md`, or `MEMORY.md` over duplicating historical implementation details.

## Transaction protocol

1. Inventory selected files: path, size, SHA-256.
2. Produce `review.json` and `summary-preview.md` without modifying sources.
3. Run `python3 scripts/check_review.py <run-dir>` to validate schema, actions,
   citations, and source hashes. Fix any failure before continuing.
4. Copy raw files into the slice archive and verify hashes match.
5. Write the curated summary atomically, then remove the originals.
6. Rebuild the memory index.
7. Spot-check recall for the slice's most important retained claim.
8. Commit the slice ledger only if all of the above pass; otherwise restore
   originals from the archive.

## Quality gates

- No sender/session metadata, credentials, or sensitive values in summaries.
- Every retained claim is standalone, normally one sentence, and cites its
  source lines.
- Archive hashes match the preimages exactly.
- The curated claim is retrievable after reindexing.

## Status

Slices 1-3 complete: 17 files archived, 1 claim distilled. Both decision types
are proven. Remaining raw session files can be processed in larger batches;
there is no urgency since they are searchable but never injected into context.
