---
name: retrieval-system-design
description: "Use when designing search, RAG, or knowledge graphs."
version: 0.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [search, rag, graphs, architecture, authorization]
    related_skills: [grounded-citations]
---

# Retrieval System Design

Design document search and knowledge retrieval from workload, provenance, authorization, and measured cost rather than choosing a graph product first. Cover lexical/vector search, document hierarchies, entity associations, selective claim graphs, and lazy synthesis.

## When to use

Use for architectural comparisons, corpus sizing, cross-document navigation, GraphRAG trade-offs, and permission-aware retrieval. This is a design workflow, not a claim that a proposed implementation has been benchmarked.

## Procedure

1. **Define the workload and security boundary.** Collect representative lookup, relationship, comparison, and library-wide questions. Establish document formats, update frequency, query repetition, citation needs, and document ACL semantics. Ask whether restricted existence as well as content must be concealed. Do not delay a conceptual answer for unavailable measurements: state assumptions and identify what would change the recommendation.
2. **Separate the data layers.** Model document → section → passage independently of topics, mentions, claims, and canonical entities. Preserve source spans, document versions, and extraction versions. Use multi-membership for topics rather than forcing the semantic structure to match the document tree. Distinguish hierarchy, self-similarity, and hyperedges: a collection of graphs is not automatically a hypergraph, and a scale-free degree distribution does not establish fractal structure.
3. **Establish a simpler baseline.** Compare lexical search, lexical-plus-vector retrieval, and section-to-entity associations before exhaustive triple extraction. For embedding selection, chunk boundaries, and annotation scope, read [Chunking and semantic granularity](references/chunking-and-semantic-granularity.md). Embeddings address semantic entry and vocabulary mismatch but are not mandatory. Combine independent rankings with rank fusion or calibrated scores, not an unexplained sum of incompatible scores. Retrieve relevant parent/neighbor context without requiring every passage to pass a document-summary gate.
4. **Design bounded cross-document navigation.** Enter through search, follow query-relevant canonical entities, citations, or selected typed relationships, then rerank expanded evidence. Record mention evidence and leave ambiguous identity unresolved. Downweight generic hubs and cap expansion depth, fan-out, and evidence budget. Treat co-occurrence and vector similarity as discovery signals, not identity, entailment, agreement, or causation. Use association tables where sufficient; require graph-specific storage only when traversal needs justify it.
5. **Choose precomputation separately from traversal.** Precompute reusable structure, search indexes, and selected evidence-backed domain claims. Explore adaptively at query time. Prefer document-scoped enrichment plus authorized query-time synthesis when ACLs differ. Add topic summaries for broad coverage only when needed; extract richer relationships lazily or selectively rather than treating full GraphRAG and minimal indexing as the only choices. Promote recurring validated extractions into the index, accounting for rare high-consequence questions as well as popularity.
6. **Enforce authorization before evidence use.** Resolve document authorization for every derived artifact and graph expansion; final citation filtering is insufficient. Never use inaccessible evidence as an invisible bridge between accessible documents. Track dependencies of cross-document summaries and caches. Read [Authorization and provenance](references/authorization-and-provenance.md) when ACLs apply.
7. **Estimate with explicit quantities, then evaluate.** Separate ingestion, query, maintenance, and serving costs. Calculate using `execute_code` or `terminal`; label assumptions, measurements, and quoted benchmark results separately. Read [Sizing and evaluation](references/sizing-and-evaluation.md) for formulas, acceptance tests, and public benchmark dataset selection. Never infer tokens, RAM requirements, ingestion duration, or dollar costs from page count alone.

## Response shape

Lead with the recommended combination and the decision it optimizes. Present a compact comparison of alternatives, one concrete navigation example, then cost/security caveats and the next validation criterion. Distinguish design proposals from exercised implementations and published hypotheses from measured findings. Retrieve and cite primary sources via `grounded-citations` when asserting product capabilities, current pricing, or research results; do not transfer benchmark savings to a different corpus.

## Verification

Before finalizing, check that the design answers the stated query classes, keeps source qualifiers and provenance, bounds expansion, supports source/ACL changes, and identifies where simpler retrieval would fail. For implementation work, test both relevance and adversarial authorization behavior before claiming success. For design-only work, explicitly leave empirical sizing and performance unverified rather than presenting illustrative values as measurements.
