// AnythingLLM HTTP client — used by memory_search (semantic + hybrid
// modes) and the memory-recall skill. Read-only by design: pi-memory
// queries AnythingLLM but never ingests into it. Ingestion is the
// user's existing pipeline (Obsidian → AnythingLLM via a cron).
//
// Credentials can come from config TOML or env vars (env wins):
//   ANYTHINGLLM_HOST     base URL, e.g. "http://localhost:3001"
//   ANYTHINGLLM_API_KEY  API key for "Authorization: Bearer ..."
//
// Endpoint reference: matches the open-claw-workspace knowledge-base
// skill at open-claw-workspace/skills/knowledge-base/SKILL.md.

import type { AnythingLLMConfig } from "../config/types.ts";

export interface VectorSearchHit {
	id: string;
	text: string;
	title: string;
	chunkSource: string;
	url: string;
	score: number;
}

export interface VectorSearchOptions {
	query: string;
	topN?: number;
	scoreThreshold?: number;
	signal?: AbortSignal;
}

interface RawVectorSearchResponse {
	results?: Array<{
		id?: string;
		text?: string;
		metadata?: {
			title?: string;
			url?: string;
			chunkSource?: string;
		};
		score?: number;
	}>;
	error?: string;
}

/**
 * Call /api/v1/workspace/<slug>/vector-search and return normalized hits.
 * Throws when credentials are missing or the HTTP response is non-2xx.
 */
export async function vectorSearch(
	config: AnythingLLMConfig,
	opts: VectorSearchOptions,
): Promise<VectorSearchHit[]> {
	const host = config.host;
	const key = config.api_key;
	if (!host || !key) {
		throw new Error(
			"AnythingLLM not configured. Set [anythingllm].host/api_key in config or ANYTHINGLLM_HOST/ANYTHINGLLM_API_KEY env vars.",
		);
	}
	const url = `${stripTrailingSlash(host)}/api/v1/workspace/${encodeURIComponent(config.workspace)}/vector-search`;
	const body = JSON.stringify({
		query: opts.query,
		topN: opts.topN ?? config.top_n,
		scoreThreshold: opts.scoreThreshold ?? config.score_threshold,
	});

	const res = await fetch(url, {
		method: "POST",
		headers: {
			"Authorization": `Bearer ${key}`,
			"Content-Type": "application/json",
		},
		body,
		signal: opts.signal,
	});
	if (!res.ok) {
		throw new Error(`AnythingLLM vector-search ${res.status}: ${await res.text()}`);
	}
	const json = (await res.json()) as RawVectorSearchResponse;
	if (json.error) throw new Error(`AnythingLLM vector-search error: ${json.error}`);
	const results = json.results ?? [];
	return results.map((r) => ({
		id: r.id ?? "",
		text: r.text ?? "",
		title: r.metadata?.title ?? "(untitled)",
		chunkSource: r.metadata?.chunkSource ?? "",
		url: r.metadata?.url ?? "",
		score: r.score ?? 0,
	}));
}

/**
 * Strip `<document_metadata>...</document_metadata>` blocks and leading
 * frontmatter that AnythingLLM prepends to every chunk. What's left is
 * what a human cares about reading.
 */
export function cleanChunkText(text: string): string {
	let cleaned = text.replace(/<document_metadata>[\s\S]*?<\/document_metadata>\s*/g, "");
	// Strip leading frontmatter delimited by ---
	cleaned = cleaned.replace(/^---\n[\s\S]*?\n---\s*/, "");
	return cleaned.trim();
}

/**
 * Best-effort: produce a short snippet for display (one or two lines).
 */
export function snippetFromText(text: string, maxChars = 180): string {
	const cleaned = cleanChunkText(text);
	const firstLine = cleaned.split("\n").find((l) => l.trim().length > 0) ?? "";
	return firstLine.length > maxChars ? `${firstLine.slice(0, maxChars - 3)}...` : firstLine;
}

function stripTrailingSlash(s: string): string {
	return s.endsWith("/") ? s.slice(0, -1) : s;
}
