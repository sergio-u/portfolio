# Authorization and provenance

## 1. Anchor derived content to its security source

Attach source document IDs and versions to passages, embeddings, mentions, claims, summaries, and extracted relationships. Resolve permissions through the authoritative document policy; if a search backend requires denormalized ACL fields, specify propagation, stale-index handling, and revocation behavior rather than assuming instantaneous consistency. Fail closed on unresolved authorization.

Keep document-scoped claim instances even when canonical entities are shared; merging claim wording can import confidential qualifiers into otherwise accessible facts. Treat a shared concept node as a lookup key, not permission to enumerate every occurrence. Keep independently maintained public vocabulary separate from aliases or descriptions learned only from restricted sources.

## 2. Apply permissions throughout retrieval

Filter lexical/vector candidates through a backend mechanism compatible with the required isolation. Check authorization before passing evidence to reranking, generation, tool calls, or user-visible traces. Confirm the engine's actual filtered-search semantics: removing unauthorized hits from a fixed global top set can destroy recall, while trusted internal index traversal and user-visible evidence traversal are different concerns.

At every graph expansion, authorize the relationship's supporting evidence as well as destination nodes. If A and C are accessible but their connecting fact is supported only by restricted B, do not use B to route between them. Independently retrieving C or following independently authorized support is permitted.

Apply equivalent restrictions to topic labels, summaries, autocomplete, counts, entity descriptions, and explanations. For a strict existence-hiding threat model, assess global corpus statistics, learned communities, ranking changes, and timing side channels; a permission-filtered shared index is not automatically equivalent to an index built solely from authorized documents. Use stronger isolation when required rather than promising complete noninterference from metadata filtering alone.

## 3. Model derived-artifact dependencies

| Artifact | Conservative authorization rule |
|---|---|
| Single-document summary or claim | Source document permission |
| Synthesis jointly depending on A and B | Access to both supporting documents |
| Independently supported equivalent claim | At least one complete authorized support set; serve wording and qualifiers derived only from that set |
| Cached cross-document answer | Current authorization for its full dependency set plus valid source versions |

Represent alternative complete support sets separately from jointly required evidence. A flat list of sources cannot distinguish an assertion requiring both A and B from one independently established by either.

Do not summarize all sources and then redact: restricted content can affect selection, phrasing, and conclusions even after its citations disappear. Generate from authorized evidence. Use fixed permission-cohort summaries only when the cohort and dependencies can be enforced; avoid materializing a summary for every possible user access combination.

## 4. Manage updates and caches

Version source text, extraction configuration, and authorization state. Invalidate or reauthorize cached results after revocation, group-membership changes, document edits, or deletion. Do not key solely on query text or user ID. Cache reuse across users requires equivalent effective authorization for all dependencies; enforce access again when serving the artifact.

Keep shared entities when deleting document-owned evidence, but remove obsolete mentions, claims, and derived dependencies. Do not cascade-delete canonical entities still supported elsewhere. Set explicit policies for stale derived results during asynchronous index updates.

## 5. Test adversarially

Test two users with overlapping but different document sets. Include a restricted-only bridge between accessible sources, a shared entity with a restricted-only alias, a mixed-source summary, equivalent claims with alternative support, revoked access after cache creation, and a deleted source. Verify retrieved IDs, graph paths, reranker inputs, prompts, citations, summaries, counts, and user-visible diagnostics—not just the final answer. Use private canary strings in test fixtures to detect leakage. Separately test retrieval quality under selective ACL filters.
