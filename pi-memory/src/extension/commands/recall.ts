// /recall <query> — search the memory vault.
//
// Modes:
//   --grep        local ripgrep over <vault>/80_AI/ (default unless [anythingllm].default_mode says otherwise)
//   --semantic    AnythingLLM vector-search over the configured workspace
//   --hybrid      both, semantic hits first then grep hits not already there
//   --limit N     cap result count (default 50)

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { tryLoadEffectiveConfig } from "../config/loader.ts";
import { aiRoot } from "../util/paths.ts";
import { grepMarkdown } from "../util/grep.ts";
import { vectorSearch, snippetFromText } from "../util/anythingllm.ts";

interface ParsedArgs {
	query: string;
	mode: "grep" | "semantic" | "hybrid";
	limit: number;
}

type FormattedHit =
	| { kind: "grep"; file: string; line: number; snippet: string }
	| { kind: "semantic"; title: string; chunkSource: string; score: number; snippet: string };

export function registerRecall(pi: ExtensionAPI): void {
	pi.registerCommand("recall", {
		description:
			"Search the memory vault. Default is grep over the local vault; --semantic queries AnythingLLM; --hybrid runs both.",
		handler: async (args, ctx) => {
			const loaded = tryLoadEffectiveConfig(ctx.cwd);
			if (!loaded.ok) {
				ctx.ui.notify(loaded.message);
				return;
			}
			const config = loaded.config;
			const parsed = parseArgs(args, config.anythingllm.default_mode);
			if (parsed.query.length === 0) {
				ctx.ui.notify("/recall: provide a query.");
				return;
			}

			const root = aiRoot(config);
			const collected: FormattedHit[] = [];
			const warnings: string[] = [];

			if (parsed.mode === "semantic" || parsed.mode === "hybrid") {
				try {
					const sem = await vectorSearch(config.anythingllm, {
						query: parsed.query,
						topN: parsed.limit,
					});
					for (const h of sem) {
						collected.push({
							kind: "semantic",
							title: h.title,
							chunkSource: h.chunkSource,
							score: h.score,
							snippet: snippetFromText(h.text),
						});
					}
				} catch (err) {
					const msg = err instanceof Error ? err.message : String(err);
					warnings.push(`semantic: ${msg}`);
					if (parsed.mode === "semantic") {
						ctx.ui.notify(`/recall: semantic search failed — ${msg}`);
						return;
					}
				}
			}

			if (parsed.mode === "grep" || parsed.mode === "hybrid") {
				const grep = grepMarkdown(root, parsed.query, parsed.limit);
				for (const h of grep) {
					collected.push({ kind: "grep", file: h.file, line: h.line, snippet: h.snippet });
				}
			}

			const warnLine = warnings.length > 0 ? ` (warnings: ${warnings.join("; ")})` : "";
			if (collected.length === 0) {
				ctx.ui.notify(`/recall: no matches for "${parsed.query}" (${parsed.mode})${warnLine}.`);
				return;
			}
			const formatted = collected
				.map((h, i) => {
					if (h.kind === "grep") return `${i + 1}. [grep] ${h.file}:${h.line}\n     ${h.snippet}`;
					return `${i + 1}. [semantic ${h.score.toFixed(2)}] ${h.title}\n     ${h.chunkSource}\n     ${h.snippet}`;
				})
				.join("\n");
			ctx.ui.notify(`/recall: ${collected.length} match(es) (${parsed.mode})${warnLine}\n${formatted}`);
		},
	});
}

// (parseArgs follows — flag parsing for --grep / --semantic / --hybrid / --limit N)
function parseArgs(raw: string, defaultMode: "grep" | "semantic" | "hybrid"): ParsedArgs {
	const tokens = raw.split(/\s+/).filter(Boolean);
	let mode: "grep" | "semantic" | "hybrid" = defaultMode;
	let limit = 50;
	const queryTokens: string[] = [];
	for (let i = 0; i < tokens.length; i++) {
		const t = tokens[i];
		if (t === "--semantic") { mode = "semantic"; continue; }
		if (t === "--grep") { mode = "grep"; continue; }
		if (t === "--hybrid") { mode = "hybrid"; continue; }
		if (t === "--limit") {
			const n = Number(tokens[++i]);
			if (Number.isFinite(n) && n > 0) limit = Math.floor(n);
			continue;
		}
		queryTokens.push(t);
	}
	return { query: queryTokens.join(" "), mode, limit };
}
