# Sizing and evaluation

## Establish corpus measurements

Sample representative digital PDFs, scans, tables, diagrams, and languages. Measure source bytes, extracted text bytes, token counts, chunk counts after overlap, and OCR requirements. Keep sections and retrieval chunks distinct. Use the sample distribution to project ranges; page count alone does not determine tokens or extraction throughput.

## Build an explicit capacity worksheet

Calculate with tools, not mental arithmetic. Use consistent decimal GB or binary GiB labels.

- Raw vectors: number of indexed vectors × dimensions × bytes per coordinate. Add measured ANN overhead, metadata, stored full-precision copies if retained, and index-build workspace separately. Quantization changes vector payload, not necessarily every stored copy.
- Text/search: source text, duplicated overlapping chunks, stored fields, lexical postings, and compression. Measure index expansion on the intended backend; do not assign a universal multiplier.
- Graph: counts of each node, edge, mention, and claim type, plus measured property/index overhead. Count participant, provenance, and structural edges explicitly rather than treating each claim as one edge.
- Operations: add replicas, backups, transaction logs, caches, and rebuild headroom. Distinguish steady disk footprint, peak build disk, resident memory, and working-set requirements.

Report database bytes relative to both original PDFs and extracted text. Image-heavy PDFs and compact text PDFs produce very different ratios. Never promise that a dataset fits in RAM merely because estimated disk size is below installed RAM.

## Separate cost centers

Account for extraction/OCR, embedding, claim extraction, entity resolution, summaries, index building, query-time reranking/generation, and ongoing maintenance. For model APIs, calculate input tokens and output tokens at their separate verified rates; include prompt overhead, overlap, retries, and batch discounts only when applicable. Local computation is not free: distinguish cash/API charges from CPU/GPU time and operating cost.

Estimate wall-clock time from measured throughput and actual service quotas, not worker count alone. Adding a document includes entity matching and index maintenance as well as linear text processing. Deletion includes reverse dependency invalidation; it is not necessarily a single cheap row removal.

## Control structural growth

Store section-to-entity incidence links rather than every pair of documents sharing an entity. An entity appearing in m documents can induce m(m−1)/2 undirected document pairs, although its incidence representation needs only m document memberships. Avoid dense pairwise materialization unless a demonstrated query requires it.

If storing similarity neighbors, bound neighbors per item; ANN candidate construction is separate work and does not make pairwise exact comparison free. Bound traversal by candidates, fan-out, depth, and evidence budget. Do not claim a universal ANN complexity or query latency independent of index settings, filters, degree distribution, and workload.

## Evaluate alternatives on the same questions

Compare lexical search; hybrid search; hybrid plus entity/citation expansion; selective claims; and lazy relationship extraction. Keep extraction quality and permission rules comparable. Measure evidence recall, citation correctness, unsupported conclusions, broad-topic coverage, latency distribution, build cost, query cost, and update/revocation behavior. For relation-heavy queries, score whether qualifications and complete evidence chains survive—not merely whether an entity appears in retrieved text.

Distinguish research hypotheses from findings and algorithm ideas from available product features. Lazy indexing shifts some work to queries; it does not make parsing, embeddings, operations, or repeated synthesis free. Recommend deeper indexing when measured reuse, latency, or evidence gains justify its maintenance burden.

## Public benchmark selection

Size the benchmark against the user's corpus in the same unit (documents vs pages vs tokens). ViDoRe-style corpora count PDF pages from a handful of documents (check `documents_metadata`), so they test layout realism, not scale. For "1–2 orders of magnitude larger" targets, compute the target in docs and pages first.

Verify candidates live via the HF API rather than memory: `https://huggingface.co/api/datasets?search=<q>&sort=downloads`, `https://datasets-server.huggingface.co/size?dataset=<id>` (row counts per config; fails for script-based datasets), `https://huggingface.co/api/datasets/<id>/tree/main/<dir>` (file sizes). Filter to the user's language (English-only by default here).

Useful English options with labels at scale: MLDR-en (`Shitao/MLDR`, `mldr-v1.0-en`: 200k Wikipedia docs, ~3.3k tokens avg, 800 test queries, corpus ~985 MB gz; skip train), DAPR (`UKPLab/dapr`, parent-context passage retrieval), CLERC (`jhu-clsp/CLERC`, legal). Small-but-realistic: ViDoRe V3 English domains, FinanceBench, LegalBench-RAG/CUAD. Scaling a small labeled domain set: keep its queries and add same-domain distractors (EDGAR-CORPUS, Pile of Law contracts); spot-check top hits for distractors that truly answer. Vendor RCP-nDCG scores measure reranking of a fixed candidate set, not first-stage retrieval.

## Primary-source starting points

- Rank fusion for combining independent lexical/vector rankings: https://www.elastic.co/guide/en/elasticsearch/reference/current/rrf.html
- Deferred extraction and adaptive exploration: https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/

Re-fetch relevant sources before making current capability or benchmark claims. Treat the research post's proposed richer indexes as hypotheses, not validated improvements for a new technical-document corpus.
