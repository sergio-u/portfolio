# Chunking and semantic granularity

## Separate representations

Keep canonical document text, structural sections, and source spans independent of retrieval chunks. Retrieval chunks may overlap and change with experiments; deduplicate entity mentions by source span rather than creating new knowledge for each overlapping chunk. Keep table headers, units, captions, and clause/list context attached to retrieval units. Page boundaries are citation coordinates, not default semantic boundaries.

Anchor entity mentions to exact source spans and resolve canonical identity separately. Use section-level entity and topic associations for navigation, and document-level rollups for facets and routing. Distinguish a topic a section is about from a passing mention; do not inherit every document topic onto every passage. Extraction may read a section for disambiguation while emitting passage/span-scoped evidence.

Retrieve small evidence units and expand relevant parent/neighbor context under a budget. Do not equate embedding context-window capacity with desirable chunk size. Treat chunk-size and overlap recommendations as starting hypotheses, not measured optima. Preserve exceptions, negation, qualifiers, and source references across boundaries.

## Model selection and evaluation

Retrieve current primary model documentation before asserting supported dimensions, input limits, licensing, or hosting. Compare a low-cost baseline, a higher-capacity contender, and a self-hosted candidate when privacy warrants it; benchmark on the corpus rather than selecting by a general leaderboard. Evaluate natural-language query-to-passage retrieval separately from passage-to-passage exploration, using the model's prescribed task modes/instructions. Do not compare vectors from different models as one embedding space.

Test chunk granularity on one model first, then shortlisted models on a fixed representation, then entity/topic expansion against hybrid retrieval without graph expansion. Evaluate entity-heavy passages, terminology mismatch, long clauses, tables, qualifiers, multilingual material where applicable, and selective ACL filters. Assess source evidence recall, useful related-section discovery, citation precision, duplicate results, latency, and actual bytes per source document.

Keep model version, dimensions, preprocessing, and chunking version with embeddings. Reducing dimensions and numeric precision are separate decisions; verify quality after either. Authorization at retrieval does not authorize sending source text to an external embedding provider: check data-processing and residency constraints independently.
