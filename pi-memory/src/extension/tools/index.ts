// Tool registrations: deterministic primitives the LLM and pi-memory skills call.

import * as fs from "node:fs";
import * as path from "node:path";
import { StringEnum } from "@earendil-works/pi-ai";
import type { AgentToolResult } from "@earendil-works/pi-agent-core";
import {
	DEFAULT_MAX_BYTES,
	DEFAULT_MAX_LINES,
	formatSize,
	truncateHead,
	withFileMutationQueue,
	type ExtensionAPI,
	type ExtensionContext,
	type TruncationResult,
} from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { buildBasicBlock, buildFullSlice } from "../gateway/build.ts";
import { loadEffectiveConfig } from "../config/loader.ts";
import { updateSentinelState, clearSentinelState } from "../sentinel/writer.ts";
import { readSentinel, resolveRepoName } from "../sentinel/reader.ts";
import {
	aiRoot,
	assertSafePathSegment,
	currentWeeklyFile,
	domainFile,
	expandTilde,
	projectDir,
	resolveManagedMarkdownPath,
	weeklyRoot,
} from "../util/paths.ts";
import { STATE_KEYS, type GatewayEntry } from "../util/session-state.ts";
import { appendToFile, appendToSection, setFrontmatterField } from "../util/markdown.ts";
import { grepMarkdown } from "../util/grep.ts";
import { ensureProjectScaffold, ensurePlanScaffold } from "../util/scaffold.ts";
import { vectorSearch, snippetFromText, type VectorSearchHit } from "../util/anythingllm.ts";

export function registerTools(pi: ExtensionAPI): void {
	pi.registerTool({
		name: "memory_capture",
		label: "Capture",
		description:
			"Append a formatted line to a markdown file under the managed memory roots (80_AI or weekly notes). Use memory_resolve_capture_target first instead of guessing paths. Writes are serialized through Pi's file mutation queue.",
		parameters: Type.Object({
			file: Type.String({ description: "Absolute path to the markdown file to append to." }),
			line: Type.String({ description: "The full single-line list item to append." }),
			section: Type.Optional(
				Type.String({
					description:
						"Optional Markdown section heading (e.g. '## Log', '## Inbox'). If provided, append within that section; otherwise append to EOF.",
				}),
			),
		}),
		execute: async (_id, params, _sig, _on, ctx) => {
			const { file, line, section } = params as { file: string; line: string; section?: string };
			const config = loadEffectiveConfig(ctx.cwd);
			const targetFile = resolveManagedMarkdownPath(config, file);
			await withFileMutationQueue(targetFile, async () => {
				if (section) {
					appendToSection(targetFile, section, line);
				} else {
					appendToFile(targetFile, line);
				}
			});
			return resultOk(`Wrote to ${targetFile}${section ? ` (${section})` : ""}`, {
				file: targetFile,
				section,
			});
		},
	});

	pi.registerTool({
		name: "memory_set_frontmatter",
		label: "Set frontmatter",
		description:
			"Set a single YAML frontmatter field on a markdown file under the managed memory roots. Writes are serialized through Pi's file mutation queue.",
		parameters: Type.Object({
			file: Type.String({ description: "Absolute path to the markdown file." }),
			key: Type.String({ description: "Frontmatter key (e.g. 'status')." }),
			value: Type.Union(
				[Type.String(), Type.Number(), Type.Boolean(), Type.Array(Type.String())],
				{ description: "Value to set." },
			),
		}),
		execute: async (_id, params, _sig, _on, ctx) => {
			const { file, key, value } = params as {
				file: string;
				key: string;
				value: string | number | boolean | string[];
			};
			const config = loadEffectiveConfig(ctx.cwd);
			const targetFile = resolveManagedMarkdownPath(config, file);
			await withFileMutationQueue(targetFile, async () => {
				setFrontmatterField(targetFile, key, value);
			});
			return resultOk(`Set ${key} on ${targetFile}`, { file: targetFile, key });
		},
	});

	pi.registerTool({
		name: "memory_search",
		label: "Search vault",
		description:
			"Search the memory vault. Modes: grep (local markdown search), semantic (AnythingLLM vector-search), hybrid (semantic hits first, then grep). Output is truncated to Pi's custom-tool limits.",
		parameters: Type.Object({
			query: Type.String({ description: "The search query." }),
			mode: StringEnum(["grep", "semantic", "hybrid"] as const, { description: "Search mode." }),
			limit: Type.Optional(Type.Number({ description: "Maximum results, capped at 50.", minimum: 1 })),
		}),
		execute: async (_id, params, signal, _on, ctx) => {
			const { query, mode, limit } = params as {
				query: string;
				mode: "grep" | "semantic" | "hybrid";
				limit?: number;
			};
			const config = loadEffectiveConfig(ctx.cwd);
			const root = aiRoot(config);
			const max = normalizeLimit(limit, 50);

			let grepHits: Array<{ source: "grep"; file: string; line: number; snippet: string }> = [];
			let semHits: Array<{ source: "semantic"; title: string; chunkSource: string; score: number; snippet: string }> = [];
			const warnings: string[] = [];

			if (mode === "grep" || mode === "hybrid") {
				grepHits = grepMarkdown(root, query, max).map((h) => ({
					source: "grep" as const,
					file: h.file,
					line: h.line,
					snippet: h.snippet,
				}));
			}
			if (mode === "semantic" || mode === "hybrid") {
				try {
					const sem = await vectorSearch(config.anythingllm, { query, topN: max, signal });
					semHits = sem.map(toSemanticHit);
				} catch (err) {
					const msg = err instanceof Error ? err.message : String(err);
					warnings.push(`semantic: ${msg}`);
					if (mode === "semantic") {
						return {
							content: [{ type: "text", text: `memory_search semantic mode failed: ${msg}` }],
							details: { hits: [], mode, query, warnings },
						};
					}
				}
			}

			const merged = [...semHits, ...grepHits];
			const formatted = formatSearchResult(query, mode, merged, root, warnings);
			const output = truncateToolOutput(formatted);
			return {
				content: [{ type: "text", text: output.text }],
				details: { hits: merged, mode, query, warnings, truncation: output.truncation },
			};
		},
	});

	pi.registerTool({
		name: "memory_list_projects",
		label: "List projects",
		description:
			"Return the list of known projects in the memory vault. Computed live from 80_AI/projects/ directory listing.",
		parameters: Type.Object({}),
		execute: async (_id, _params, _sig, _on, ctx) => {
			const config = loadEffectiveConfig(ctx.cwd);
			const dir = path.join(aiRoot(config), "projects");
			const names = listSubdirs(dir);
			return resultOk(`${names.length} project(s): ${names.join(", ") || "(none)"}`, { names });
		},
	});

	pi.registerTool({
		name: "memory_list_domains",
		label: "List domains",
		description:
			"Return the list of known domains in the memory vault. Includes both topic domains and repo-as-domain pages.",
		parameters: Type.Object({}),
		execute: async (_id, _params, _sig, _on, ctx) => {
			const config = loadEffectiveConfig(ctx.cwd);
			const dir = path.join(aiRoot(config), "domains");
			const names = listMarkdownBasenames(dir);
			return resultOk(`${names.length} domain(s): ${names.join(", ") || "(none)"}`, { names });
		},
	});

	pi.registerTool({
		name: "memory_list_projects_by_tag",
		label: "Projects by tag",
		description:
			"Return projects whose project.md frontmatter includes the given tag. Useful for 'which projects use repo X?' or 'which projects touch csharp?'.",
		parameters: Type.Object({
			tag: Type.String({ description: "The tag to filter by (domain or repo name)." }),
		}),
		execute: async (_id, params, _sig, _on, ctx) => {
			const { tag } = params as { tag: string };
			const config = loadEffectiveConfig(ctx.cwd);
			const dir = path.join(aiRoot(config), "projects");
			const names = listSubdirs(dir).filter((name) =>
				projectFrontmatterHasTag(path.join(dir, name, "project.md"), tag),
			);
			return resultOk(`${names.length} project(s) tagged '${tag}': ${names.join(", ") || "(none)"}`, { tag, names });
		},
	});

	pi.registerTool({
		name: "memory_get_context",
		label: "Current context",
		description:
			"Return the current memory context, resolved capture roots, and note-routing flags. Read-only.",
		parameters: Type.Object({}),
		execute: async (_id, _params, _sig, _on, ctx) => {
			const config = loadEffectiveConfig(ctx.cwd);
			const sentinel = readSentinel(ctx.cwd);
			const repo = resolveRepoName(ctx.cwd, sentinel);
			const result = {
				repo,
				project: sentinel?.state.projects[0] ?? null,
				plan: sentinel?.state.plan ?? null,
				domains: activeDomains(config, repo, sentinel?.state.domains ?? []),
				paths: captureRoots(config),
				note: {
					auto_create_domains: config.note.auto_create_domains,
					multi_target: config.note.multi_target,
				},
			};
			return resultOk(formatContextSummary(result), result);
		},
	});

	pi.registerTool({
		name: "memory_resolve_capture_target",
		label: "Resolve capture target",
		description:
			"Resolve a symbolic capture target to a validated markdown file and optional section. Use target=current for normal note routing, weekly for the current weekly inbox, or domain with a domain name for a known domain page.",
		parameters: Type.Object({
			target: Type.Optional(StringEnum(["current", "weekly", "domain"] as const, { description: "Target to resolve." })),
			domain: Type.Optional(Type.String({ description: "Domain name for target=domain, without .md." })),
		}),
		execute: async (_id, params, _sig, _on, ctx) => {
			const { target, domain } = params as { target?: "current" | "weekly" | "domain"; domain?: string };
			const config = loadEffectiveConfig(ctx.cwd);
			const resolved = resolveCaptureTarget(config, ctx, target ?? "current", domain);
			return resultOk(formatCaptureTarget(resolved), {
				target: resolved,
				paths: captureRoots(config),
				note: {
					auto_create_domains: config.note.auto_create_domains,
					multi_target: config.note.multi_target,
				},
			});
		},
	});

	pi.registerTool({
		name: "memory_set_context",
		label: "Set context",
		description:
			"Update the per-branch memory context. Path syntax: 'project' or 'project/plan'. Use '/' or '~' to clear. Idempotent; creates project/plan scaffolds and refreshes the gateway.",
		parameters: Type.Object({
			path: Type.String({
				description:
					"The context path. Examples: 'pi-memory', 'pi-memory/v1-ext', '/', '~'.",
			}),
		}),
		execute: async (_id, params, _sig, _on, ctx) => {
			const { path: p } = params as { path: string };
			const config = loadEffectiveConfig(ctx.cwd);
			if (p === "/" || p === "~") {
				clearSentinelState(ctx.cwd);
				appendGatewayEntry(pi, ctx.cwd, false);
				return resultOk("Cleared memory context. Captures route to weekly inbox.", { cleared: true });
			}

			const parsed = parseContextPath(p);
			await ensureProjectScaffold(config, parsed.project, config.state.domains);
			const planPath = parsed.plan ? `plans/${parsed.plan}` : "";
			if (parsed.plan) {
				await ensurePlanScaffold(config, parsed.project, parsed.plan);
			}

			updateSentinelState(ctx.cwd, {
				projects: [parsed.project],
				plan: planPath,
			});
			appendGatewayEntry(pi, ctx.cwd, true);

			return resultOk(
				`Set context: project=${parsed.project}` +
					(parsed.plan ? `, plan=${parsed.plan}` : "") +
					". Full gateway refreshed.",
				parsed,
			);
		},
	});

	pi.registerTool({
		name: "memory_dream_stats",
		label: "Dream stats",
		description:
			"Return Dream-pass diagnostics: timestamp of last dream, days since, and count of vault files modified during the current awake period.",
		parameters: Type.Object({}),
		execute: async (_id, _params, _sig, _on, ctx) => {
			const config = loadEffectiveConfig(ctx.cwd);
			const marker = path.join(aiRoot(config), ".last_dream.marker");
			let lastDreamAt: string | null = null;
			let daysSince: number | null = null;
			if (fs.existsSync(marker)) {
				const mtime = fs.statSync(marker).mtime;
				lastDreamAt = mtime.toISOString();
				daysSince = Math.floor((Date.now() - mtime.getTime()) / (1000 * 60 * 60 * 24));
			}
			const awakeFiles = countModifiedFiles(config, marker);
			return resultOk(
				lastDreamAt
					? `Last dream: ${lastDreamAt} (${daysSince}d ago). Awake-period files: ${awakeFiles}.`
					: `No dream yet. Awake-period files: ${awakeFiles}.`,
				{ last_dream_at: lastDreamAt, days_since: daysSince, awake_period_files: awakeFiles },
			);
		},
	});
}

function resultOk<T>(text: string, details: T): AgentToolResult<T> {
	return { content: [{ type: "text", text }], details };
}

interface CaptureTarget {
	file: string;
	section?: string;
	label: string;
	kind: "current" | "weekly" | "domain";
}

interface CaptureRoots {
	vault_root: string;
	ai_root: string;
	weekly_root: string;
	current_weekly_file: string;
	weekly_inbox: string;
}

function captureRoots(config: ReturnType<typeof loadEffectiveConfig>): CaptureRoots {
	return {
		vault_root: path.resolve(expandTilde(config.vault.root)),
		ai_root: path.resolve(aiRoot(config)),
		weekly_root: path.resolve(weeklyRoot(config)),
		current_weekly_file: currentWeeklyFile(config),
		weekly_inbox: config.vault.weekly_inbox,
	};
}

function resolveCaptureTarget(
	config: ReturnType<typeof loadEffectiveConfig>,
	ctx: ExtensionContext,
	target: "current" | "weekly" | "domain",
	domain?: string,
): CaptureTarget {
	if (target === "weekly") {
		return {
			file: resolveManagedMarkdownPath(config, currentWeeklyFile(config)),
			section: config.vault.weekly_inbox,
			label: "weekly inbox",
			kind: "weekly",
		};
	}
	if (target === "domain") {
		return resolveDomainCaptureTarget(config, domain);
	}

	const sentinel = readSentinel(ctx.cwd);
	const projectName = sentinel?.state.projects[0]
		? assertSafePathSegment(sentinel.state.projects[0], "project")
		: undefined;
	const planPath = sentinel?.state.plan ? normalizePlanPath(sentinel.state.plan) : "";
	if (projectName && planPath) {
		return {
			file: resolveManagedMarkdownPath(config, path.join(projectDir(config, projectName), planPath, "plan.md")),
			section: "## Log",
			label: `plan ${planPath}`,
			kind: "current",
		};
	}
	if (projectName) {
		return {
			file: resolveManagedMarkdownPath(config, path.join(projectDir(config, projectName), "notes.md")),
			label: `project ${projectName}`,
			kind: "current",
		};
	}
	return resolveCaptureTarget(config, ctx, "weekly");
}

function resolveDomainCaptureTarget(
	config: ReturnType<typeof loadEffectiveConfig>,
	domain?: string,
): CaptureTarget {
	if (!domain) throw new Error("target=domain requires a domain name");
	const name = normalizeDomainName(domain);
	const file = resolveManagedMarkdownPath(config, domainFile(config, name));
	if (!fs.existsSync(file) && !config.note.auto_create_domains) {
		throw new Error(`domain '${name}' does not exist and [note].auto_create_domains is false`);
	}
	return { file, label: `domain ${name}`, kind: "domain" };
}

function normalizeDomainName(domain: string): string {
	const withoutExt = domain.trim().replace(/\.md$/i, "");
	return assertSafePathSegment(withoutExt, "domain");
}

function formatCaptureTarget(target: CaptureTarget): string {
	return `Resolved ${target.label}: ${target.file}${target.section ? ` (${target.section})` : ""}`;
}

function normalizeLimit(limit: number | undefined, fallback: number): number {
	if (!Number.isFinite(limit)) return fallback;
	return Math.max(1, Math.min(Math.floor(limit ?? fallback), 50));
}

function truncateToolOutput(text: string): { text: string; truncation?: TruncationResult } {
	const truncation = truncateHead(text, { maxLines: DEFAULT_MAX_LINES, maxBytes: DEFAULT_MAX_BYTES });
	if (!truncation.truncated) return { text: truncation.content };
	const omittedLines = truncation.totalLines - truncation.outputLines;
	const omittedBytes = truncation.totalBytes - truncation.outputBytes;
	return {
		text:
			truncation.content +
			`\n\n[Output truncated: showing ${truncation.outputLines} of ${truncation.totalLines} lines ` +
			`(${formatSize(truncation.outputBytes)} of ${formatSize(truncation.totalBytes)}). ` +
			`${omittedLines} lines (${formatSize(omittedBytes)}) omitted. Use a narrower query or lower limit.]`,
		truncation,
	};
}

function listSubdirs(dir: string): string[] {
	if (!fs.existsSync(dir)) return [];
	return fs.readdirSync(dir, { withFileTypes: true })
		.filter((d) => d.isDirectory())
		.map((d) => d.name)
		.sort();
}

function listMarkdownBasenames(dir: string): string[] {
	if (!fs.existsSync(dir)) return [];
	return fs.readdirSync(dir, { withFileTypes: true })
		.filter((d) => d.isFile() && d.name.endsWith(".md"))
		.map((d) => d.name.replace(/\.md$/, ""))
		.sort();
}

function projectFrontmatterHasTag(projectMdPath: string, tag: string): boolean {
	if (!fs.existsSync(projectMdPath)) return false;
	const text = fs.readFileSync(projectMdPath, "utf8");
	const fm = text.match(/^---\n([\s\S]*?)\n---/);
	if (!fm) return false;
	const tagsLine = fm[1].split("\n").find((l) => /^tags:/.test(l.trim()));
	if (!tagsLine) return false;
	return new RegExp(`(^|[\\s\\[,'"])${escapeRegex(tag)}([\\s\\],'"]|$)`).test(tagsLine);
}

function activeDomains(
	config: ReturnType<typeof loadEffectiveConfig>,
	repo: string,
	values: string[],
): string[] {
	const domains = values.map((value) => value.trim()).filter(isSafeDomainName);
	const repoDomain = repo.trim();
	if (isSafeDomainName(repoDomain) && fs.existsSync(domainFile(config, repoDomain)) && !domains.includes(repoDomain)) {
		domains.push(repoDomain);
	}
	return domains;
}

function isSafeDomainName(value: string): boolean {
	return (
		value.length > 0 &&
		value !== "." &&
		value !== ".." &&
		!value.includes("/") &&
		!value.includes("\\") &&
		!value.includes("\0")
	);
}

function escapeRegex(s: string): string {
	return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function parseContextPath(p: string): { project: string; plan?: string } {
	const parts = p.split("/").map((s) => s.trim()).filter(Boolean);
	if (parts.length === 0) throw new Error(`empty path: '${p}'`);
	if (parts.length > 2) throw new Error(`too many context path segments: '${p}'`);
	return {
		project: assertSafePathSegment(parts[0], "project"),
		plan: parts[1] ? assertSafePathSegment(parts[1], "plan") : undefined,
	};
}

function normalizePlanPath(planPath: string): string {
	const parts = planPath.split("/").map((s) => s.trim()).filter(Boolean);
	if (parts.length !== 2 || parts[0] !== "plans") {
		throw new Error(`invalid plan path: ${planPath}`);
	}
	return `plans/${assertSafePathSegment(parts[1], "plan")}`;
}

function appendGatewayEntry(pi: ExtensionAPI, cwd: string, full: boolean): void {
	const config = loadEffectiveConfig(cwd);
	const sentinel = readSentinel(cwd);
	const repo = resolveRepoName(cwd, sentinel);
	const content = full
		? buildFullSlice({
			config,
			repo,
			notesTailLines: config.gateway.notes_tail_lines,
			tokenBudget: config.gateway.token_budget,
		})
		: buildBasicBlock({ config, repo });
	const entry: GatewayEntry = { level: full ? "full" : "basic", content, ts: new Date().toISOString() };
	pi.appendEntry(STATE_KEYS.GATEWAY, entry);
}

function countModifiedFiles(
	config: ReturnType<typeof loadEffectiveConfig>,
	marker: string,
): number {
	const root = aiRoot(config);
	if (!fs.existsSync(root)) return 0;
	const since = fs.existsSync(marker) ? fs.statSync(marker).mtime.getTime() : 0;
	let count = 0;
	const walk = (dir: string): void => {
		for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
			const full = path.join(dir, entry.name);
			if (entry.isDirectory()) {
				if (entry.name === "archive") continue;
				walk(full);
			} else if (entry.isFile() && full.endsWith(".md")) {
				if (fs.statSync(full).mtime.getTime() > since) count++;
			}
		}
	};
	walk(root);
	return count;
}

function toSemanticHit(h: VectorSearchHit): {
	source: "semantic";
	title: string;
	chunkSource: string;
	score: number;
	snippet: string;
} {
	return {
		source: "semantic",
		title: h.title,
		chunkSource: h.chunkSource,
		score: h.score,
		snippet: snippetFromText(h.text),
	};
}

type SearchHit =
	| { source: "grep"; file: string; line: number; snippet: string }
	| { source: "semantic"; title: string; chunkSource: string; score: number; snippet: string };

function formatSearchResult(
	query: string,
	mode: "grep" | "semantic" | "hybrid",
	hits: SearchHit[],
	root: string,
	warnings: string[],
): string {
	const warnLine = warnings.length > 0 ? ` (warnings: ${warnings.join("; ")})` : "";
	if (hits.length === 0) {
		return mode === "grep"
			? `No matches for "${query}" in ${root}${warnLine}.`
			: `No matches for "${query}"${warnLine}.`;
	}
	const lines = hits.map((h) => {
		if (h.source === "grep") return `  [grep] ${h.file}:${h.line}  ${h.snippet}`;
		return `  [semantic ${h.score.toFixed(2)}] ${h.title}  (${h.chunkSource})  ${h.snippet}`;
	});
	return `Found ${hits.length} match(es) for "${query}" (${mode})${warnLine}:\n${lines.join("\n")}`;
}

function formatContextSummary(c: {
	repo: string;
	project: string | null;
	plan: string | null;
	domains?: string[];
}): string {
	const parts = [`repo=${c.repo}`];
	parts.push(c.project ? `project=${c.project}` : "project=(none)");
	parts.push(c.plan ? `plan=${c.plan}` : "plan=(none)");
	if (c.domains && c.domains.length > 0) parts.push(`domains=${c.domains.join(",")}`);
	return parts.join("  ");
}
