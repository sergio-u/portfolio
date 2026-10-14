// /dump and /organize-dump -- low-friction weekly inbox workflow.

import * as fs from "node:fs";
import * as path from "node:path";
import { complete, type Api, type Message, type Model } from "@earendil-works/pi-ai";
import { withFileMutationQueue, type ExtensionAPI, type ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import { loadEffectiveConfig, tryLoadEffectiveConfig } from "../config/loader.ts";
import { aiRoot, currentWeeklyFile, resolveManagedMarkdownPath, weeklyRoot } from "../util/paths.ts";
import { ensureWeeklyNote } from "../util/weekly.ts";

interface OrganizeArgs {
	days: number;
	weeks?: number;
	currentWeek: boolean;
	applyRequested: boolean;
}

interface InboxItem {
	file: string;
	line: number;
	text: string;
}

const DUMP_INGEST_SYSTEM_PROMPT = `You ingest raw personal memory captures into Obsidian-ready Markdown.

The input may contain links, code snippets, commands, JSON, SQL, resources, people/team names, GUIDs, identifiers, open questions, todo-like notes, or handwritten daily notes.

Rules:
- Return Markdown only. No preamble, no explanation.
- Do not use the word "dump" unless it appears in the input.
- Preserve URLs, commands, code, GUIDs, identifiers, and quoted strings exactly.
- Do not invent context. If context is missing, keep the note brief and literal.
- If the input is one coherent topic, do not bucket it. Use one top-level bullet with nested details.
- If the input is clearly mixed, group related items under at most these top-level buckets: Links, Snippets, Resources, Questions / Follow-ups, Learnings / Gotchas, Misc.
- Do not create empty buckets. Do not use every bucket unless the input clearly needs them.
- Links: docs, dashboards, PRs, wiki pages, GitHub links, ADO links, SharePoint links, and Kusto dashboards.
- Snippets: commands, SQL, Kusto, PowerShell, JSON payloads, scripts, paths, and runbook fragments.
- Resources: people, teams, owners, clusters, app IDs, tenant IDs, case IDs, job IDs, paths, named services, and reusable identifiers.
- Questions / Follow-ups: open questions, investigate-later items, and weak todo-like notes.
- Learnings / Gotchas: surprising behavior, troubleshooting discoveries, and short lessons.
- Misc: one-off fragments with unclear context. Use sparingly.
- Use nested bullets for related details and resources.
- Use Markdown links when the input has a clear label followed by a URL.
- Use fenced code blocks for commands, JSON, SQL, scripts, or multi-line technical snippets.
- Prefer "Questions / Follow-ups" over "Todo" unless the user explicitly wrote todo/task.
- For resources or people, keep the name and the reason/context if present.
- For handwritten notes, preserve the order and lightly group related bullets.
- Keep the result compact and scannable in Obsidian.
- Do not decide project/domain destinations; this command only prepares weekly-inbox content.`;

const TOPIC_RULES: Array<{ topic: string; terms: string[] }> = [
	{ topic: "jj", terms: ["jj ", "jujutsu", "trunk()"] },
	{ topic: "ipam", terms: ["ipam"] },
	{ topic: "nsp", terms: ["nsp", "network security perimeter"] },
	{ topic: "azure-networking", terms: ["azure networking", "service tag", "virtual network"] },
	{ topic: "kusto", terms: ["kusto", "dataexplorer", "adx", "cluster"] },
	{ topic: "powershell", terms: ["powershell", "invoke-", "get-", "set-", ".ps1"] },
	{ topic: "sql", terms: ["select ", "update ", "delete from", "dbo."] },
	{ topic: "windows", terms: ["windows", "remote desktop", "rdp"] },
	{ topic: "openssh", terms: ["openssh", "win32-openssh"] },
	{ topic: "icm", terms: ["icm", "incident"] },
	{ topic: "devbox", terms: ["dev box", "devbox"] },
	{ topic: "spo", terms: ["sharepoint", "spo", "sptimerjob"] },
];

export function registerDumpCommands(pi: ExtensionAPI): void {
	pi.registerCommand("dump", {
		description:
			"Append a low-friction raw note to the weekly memory inbox. Always writes to weekly, grouped by day.",
		handler: async (args, ctx) => {
			const text = args.trim();
			if (text.length === 0) {
				ctx.ui.notify("/dump: provide text to dump.");
				return;
			}

			const loaded = tryLoadEffectiveConfig(ctx.cwd);
			if (!loaded.ok) {
				ctx.ui.notify(loaded.message);
				return;
			}
			const config = loaded.config;
			const formatted = await ingestDumpForInbox(text, config, ctx);
			const weekly = resolveManagedMarkdownPath(config, currentWeeklyFile(config));
			await withFileMutationQueue(weekly, async () => {
				ensureWeeklyNote(config, weekly);
				appendDumpEntry(weekly, config.vault.weekly_inbox, formatted.lines, {
					groupByDay: config.dump.group_by_day,
				});
			});
			const suffix = formatted.warning ? ` (${formatted.warning})` : "";
			ctx.ui.notify(`dumped to weekly inbox -> ${weekly}${suffix}`);
		},
	});

	pi.registerCommand("organize-dump", {
		description:
			"Review recent weekly inbox dumps and propose conservative organization. Dry-run only in this version.",
		handler: async (args, ctx) => {
			const loaded = tryLoadEffectiveConfig(ctx.cwd);
			if (!loaded.ok) {
				ctx.ui.notify(loaded.message);
				return;
			}
			const config = loaded.config;
			const parsed = parseOrganizeArgs(args, config.organize.default_window_days);
			const files = selectWeeklyFiles(config, parsed);
			const items = files.flatMap((file) => extractInboxItems(file, config.vault.weekly_inbox));
			const report = buildOrganizeReport(config, parsed, files, items);
			ctx.ui.notify(report);
		},
	});
}

async function ingestDumpForInbox(
	text: string,
	config: ReturnType<typeof loadEffectiveConfig>,
	ctx: ExtensionCommandContext,
): Promise<{ lines: string[]; warning?: string }> {
	const now = new Date();
	const modelResult = await ingestDumpWithModel(text, config.dump.ingest_model, ctx);
	if (modelResult.ok) {
		return { lines: addOptionalTimePrefix(modelResult.lines, now, config.dump.include_time) };
	}
	const lines = rawDumpEntry(text, now, config.dump.include_time);
	return modelResult.warning ? { lines, warning: modelResult.warning } : { lines };
}

async function ingestDumpWithModel(
	text: string,
	formatModel: string,
	ctx: ExtensionCommandContext,
): Promise<{ ok: true; lines: string[] } | { ok: false; warning?: string }> {
	const modelName = formatModel.trim();
	if (!modelName) return { ok: false };
	const model = resolveIngesterModel(modelName, ctx);
	if (!model) return { ok: false, warning: `ingester model '${modelName}' unavailable; used raw capture` };

	try {
		const auth = await ctx.modelRegistry.getApiKeyAndHeaders(model);
		if (!auth.ok || !auth.apiKey) {
			const reason = auth.ok ? `no API key for ${model.provider}` : auth.error;
			return { ok: false, warning: `${reason}; used raw capture` };
		}

		const userMessage: Message = {
			role: "user",
			content: [{ type: "text", text }],
			timestamp: Date.now(),
		};
		const response = await complete(
			model,
			{ systemPrompt: DUMP_INGEST_SYSTEM_PROMPT, messages: [userMessage] },
			{ apiKey: auth.apiKey, headers: auth.headers, maxTokens: 2048, temperature: 0 },
		);
		if (response.stopReason === "aborted") return { ok: false, warning: "ingester aborted; used raw capture" };
		if (response.stopReason === "error") {
			const reason = response.errorMessage ? `: ${response.errorMessage}` : "";
			return { ok: false, warning: `ingester failed${reason}; used raw capture` };
		}

		const markdown = response.content
			.filter((content): content is { type: "text"; text: string } => content.type === "text")
			.map((content) => content.text)
			.join("\n");
		const lines = normalizeModelDumpMarkdown(markdown);
		return lines.length > 0 ? { ok: true, lines } : { ok: false, warning: "ingester returned empty output; used raw capture" };
	} catch {
		return { ok: false, warning: "ingester threw; used raw capture" };
	}
}

function resolveIngesterModel(modelName: string, ctx: ExtensionCommandContext): Model<Api> | null {
	if (modelName === "default") return ctx.model ?? null;
	const slash = modelName.indexOf("/");
	if (slash <= 0 || slash === modelName.length - 1) return null;
	const provider = modelName.slice(0, slash);
	const modelId = modelName.slice(slash + 1);
	return ctx.modelRegistry.find(provider, modelId) ?? null;
}

function normalizeModelDumpMarkdown(markdown: string): string[] {
	let lines = trimOuterBlankLines(markdown.split(/\r?\n/).map((line) => line.trimEnd()));
	if (lines[0]?.trim() === "```markdown" || lines[0]?.trim() === "```") {
		lines = lines.slice(1);
		if (lines[lines.length - 1]?.trim() === "```") lines = lines.slice(0, -1);
		lines = trimOuterBlankLines(lines);
	}
	if (lines.length === 0) return [];
	if (!lines.some((line) => /^[-*]\s+/.test(line))) return [];
	return lines;
}

function addOptionalTimePrefix(lines: string[], now: Date, includeTime: boolean): string[] {
	if (!includeTime || lines.length === 0) return lines;
	const copy = [...lines];
	const firstBullet = copy.findIndex((line) => /^[-*]\s+/.test(line));
	if (firstBullet >= 0) {
		copy[firstBullet] = copy[firstBullet].replace(/^([-*]\s+)/, `$1[${formatTime(now)}] `);
	}
	return copy;
}

function appendDumpEntry(
	file: string,
	inboxHeading: string,
	entryLines: string[],
	options: { groupByDay: boolean },
): void {
	const now = new Date();
	const existing = fs.readFileSync(file, "utf8");
	const lines = existing.split("\n");
	const inboxIdx = ensureHeading(lines, inboxHeading);
	const inboxLevel = headingLevel(inboxHeading) ?? 2;

	if (!options.groupByDay) {
		const inboxEnd = findSectionEnd(lines, inboxIdx, inboxLevel);
		const insertAt = trimBlankBefore(lines, inboxEnd, inboxIdx + 1);
		lines.splice(insertAt, 0, ...entryLines);
		fs.writeFileSync(file, lines.join("\n"), "utf8");
		return;
	}

	const dayHeading = `### ${formatDate(now)}`;
	let inboxEnd = findSectionEnd(lines, inboxIdx, inboxLevel);
	let dayIdx = -1;
	for (let i = inboxIdx + 1; i < inboxEnd; i++) {
		if (lines[i].trim() === dayHeading) {
			dayIdx = i;
			break;
		}
	}

	if (dayIdx === -1) {
		const insertAt = trimBlankBefore(lines, inboxEnd, inboxIdx + 1);
		lines.splice(insertAt, 0, "", dayHeading, "", ...entryLines, "");
	} else {
		const dayEnd = findSectionEnd(lines, dayIdx, 3);
		const insertAt = trimBlankBefore(lines, Math.min(dayEnd, inboxEnd), dayIdx + 1);
		lines.splice(insertAt, 0, ...entryLines);
	}
	fs.writeFileSync(file, lines.join("\n"), "utf8");
}

function ensureHeading(lines: string[], heading: string): number {
	const idx = lines.findIndex((line) => line.trim() === heading.trim());
	if (idx !== -1) return idx;
	while (lines.length > 0 && lines[lines.length - 1].trim() === "") lines.pop();
	lines.push("", heading, "");
	return lines.length - 2;
}

function rawDumpEntry(text: string, now: Date, includeTime: boolean): string[] {
	const prefix = includeTime ? `[${formatTime(now)}] ` : "";
	const rawLines = trimOuterBlankLines(text.split(/\r?\n/).map((line) => line.trimEnd()));
	const body = rawLines.length > 0 ? rawLines : [text.trim() || "raw capture"];
	return [`- ${prefix}Raw capture`, "  ```text", ...body.map((line) => `  ${line}`), "  ```"];
}

function trimOuterBlankLines(lines: string[]): string[] {
	let start = 0;
	let end = lines.length;
	while (start < end && lines[start].trim() === "") start++;
	while (end > start && lines[end - 1].trim() === "") end--;
	return lines.slice(start, end);
}

function parseOrganizeArgs(raw: string, defaultDays: number): OrganizeArgs {
	const tokens = raw.split(/\s+/).filter(Boolean);
	const parsed: OrganizeArgs = {
		days: defaultDays,
		currentWeek: false,
		applyRequested: false,
	};
	for (let i = 0; i < tokens.length; i++) {
		const token = tokens[i];
		if (token === "--dry-run") continue;
		if (token === "--apply") { parsed.applyRequested = true; continue; }
		if (token === "--current-week") { parsed.currentWeek = true; continue; }
		if (token === "--weeks") {
			const n = Number(tokens[++i]);
			if (Number.isFinite(n) && n > 0) parsed.weeks = Math.floor(n);
			continue;
		}
		if (token === "--days" || token === "--since") {
			const next = tokens[++i] ?? "";
			const n = Number(next.replace(/d$/i, ""));
			if (Number.isFinite(n) && n > 0) parsed.days = Math.floor(n);
			continue;
		}
	}
	return parsed;
}

function selectWeeklyFiles(config: ReturnType<typeof loadEffectiveConfig>, args: OrganizeArgs): string[] {
	const root = weeklyRoot(config);
	if (!fs.existsSync(root)) return [];
	const files = fs.readdirSync(root, { withFileTypes: true })
		.filter((entry) => entry.isFile() && entry.name.endsWith(".md"))
		.map((entry) => path.join(root, entry.name));
	if (args.currentWeek) {
		const current = currentWeeklyFile(config);
		return fs.existsSync(current) ? [current] : [];
	}
	if (args.weeks !== undefined) {
		return files.sort((a, b) => a.localeCompare(b)).slice(-args.weeks);
	}
	const cutoff = Date.now() - args.days * 24 * 60 * 60 * 1000;
	return files
		.filter((file) => fs.statSync(file).mtime.getTime() >= cutoff)
		.sort((a, b) => a.localeCompare(b));
}

function extractInboxItems(file: string, inboxHeading: string): InboxItem[] {
	if (!fs.existsSync(file)) return [];
	const lines = fs.readFileSync(file, "utf8").split("\n");
	const inboxIdx = lines.findIndex((line) => line.trim() === inboxHeading.trim());
	if (inboxIdx === -1) return [];
	const inboxLevel = headingLevel(inboxHeading) ?? 2;
	const inboxEnd = findSectionEnd(lines, inboxIdx, inboxLevel);
	const items: InboxItem[] = [];

	for (let i = inboxIdx + 1; i < inboxEnd; i++) {
		const line = lines[i];
		const trimmed = line.trim();
		if (trimmed.length === 0 || headingLevel(trimmed) !== null) continue;
		const bullet = line.match(/^[-*]\s+(.*)$/);
		if (bullet) {
			const block = [bullet[1]];
			const startLine = i + 1;
			let j = i + 1;
			while (j < inboxEnd && !lines[j].match(/^[-*]\s+/)) {
				const continuation = lines[j].trim();
				if (continuation.length > 0 && headingLevel(continuation) === null) block.push(continuation);
				j++;
			}
			items.push({ file, line: startLine, text: cleanItemText(block) });
			i = j - 1;
		} else {
			items.push({ file, line: i + 1, text: cleanItemText([trimmed]) });
		}
	}
	return items.filter((item) => item.text.length > 0);
}

function cleanItemText(lines: string[]): string {
	return lines
		.map((line) => line.replace(/^>\s?/, "").replace(/^[-*]\s+/, "").replace(/^\[[0-9]{2}:[0-9]{2}\]\s*/, "").trim())
		.filter((line) => line.length > 0 && !line.startsWith("```"))
		.join(" ")
		.replace(/\s+/g, " ")
		.trim();
}

function buildOrganizeReport(
	config: ReturnType<typeof loadEffectiveConfig>,
	args: OrganizeArgs,
	files: string[],
	items: InboxItem[],
): string {
	const domains = listDomainNames(config);
	const domainPromotions = new Map<string, InboxItem[]>();
	const snippetCandidates: InboxItem[] = [];
	const topicCandidates = new Map<string, InboxItem[]>();
	const keep: InboxItem[] = [];

	for (const item of items) {
		const matchedDomains = config.organize.prefer_existing_domains
			? domains.filter((domain) => matchesDomain(item.text, domain))
			: [];
		if (matchedDomains.length > 0) {
			for (const domain of matchedDomains) addMapItem(domainPromotions, domain, item);
			continue;
		}
		const topics = detectTopics(item.text).filter((topic) => !domains.includes(topic));
		for (const topic of topics) addMapItem(topicCandidates, topic, item);
		if (looksLikeSnippet(item.text)) {
			snippetCandidates.push(item);
		} else {
			keep.push(item);
		}
	}

	const lines: string[] = [];
	lines.push("/organize-dump: dry-run only in this version.");
	if (args.applyRequested) lines.push("--apply was requested but apply mode is not implemented yet.");
	lines.push(`Window: ${args.currentWeek ? "current week" : args.weeks ? `${args.weeks} week(s)` : `${args.days} day(s)`}`);
	lines.push(`Files scanned: ${files.length}. Inbox items found: ${items.length}.`);
	lines.push(`New domain creation: ${config.organize.auto_create_domains ? "allowed by config, but still manual in this version" : "disabled"}.`);
	lines.push("Project-specific promotions are not inferred from the current repo; choose them manually during review.");
	lines.push("");

	appendDomainSection(lines, "Promote to existing domains", domainPromotions, domains, config, 8);
	appendItemSection(lines, "Possible project/runbook snippets", snippetCandidates, 10);
	appendCandidateDomains(lines, topicCandidates, config.organize.min_items_for_domain_suggestion, 8);
	appendItemSection(lines, "Keep in weekly inbox for now", keep, 12);

	return limitReport(lines.join("\n"));
}

function appendItemSection(lines: string[], title: string, items: InboxItem[], limit: number): void {
	lines.push(`## ${title}`);
	if (items.length === 0) {
		lines.push("- none", "");
		return;
	}
	for (const item of items.slice(0, limit)) {
		lines.push(`- ${formatItem(item)}`);
	}
	if (items.length > limit) lines.push(`- ... ${items.length - limit} more`);
	lines.push("");
}

function appendDomainSection(
	lines: string[],
	title: string,
	promotions: Map<string, InboxItem[]>,
	domains: string[],
	config: ReturnType<typeof loadEffectiveConfig>,
	limitPerDomain: number,
): void {
	lines.push(`## ${title}`);
	if (promotions.size === 0) {
		lines.push("- none", "");
		return;
	}
	for (const [domain, items] of [...promotions.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
		const domainPath = path.join(aiRoot(config), "domains", `${domain}.md`);
		const label = domains.includes(domain) ? domainPath : domain;
		lines.push(`- ${domain} -> ${label}`);
		for (const item of items.slice(0, limitPerDomain)) lines.push(`  - ${formatItem(item)}`);
		if (items.length > limitPerDomain) lines.push(`  - ... ${items.length - limitPerDomain} more`);
	}
	lines.push("");
}

function appendCandidateDomains(
	lines: string[],
	candidates: Map<string, InboxItem[]>,
	threshold: number,
	limitPerDomain: number,
): void {
	lines.push(`## Candidate new domains (manual only; threshold ${threshold})`);
	const eligible = [...candidates.entries()]
		.filter(([, items]) => items.length >= threshold)
		.sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]));
	if (eligible.length === 0) {
		lines.push("- none", "");
		return;
	}
	for (const [topic, items] of eligible) {
		lines.push(`- ${topic} (${items.length} items)`);
		for (const item of items.slice(0, limitPerDomain)) lines.push(`  - ${formatItem(item)}`);
		if (items.length > limitPerDomain) lines.push(`  - ... ${items.length - limitPerDomain} more`);
	}
	lines.push("");
}

function listDomainNames(config: ReturnType<typeof loadEffectiveConfig>): string[] {
	const dir = path.join(aiRoot(config), "domains");
	if (!fs.existsSync(dir)) return [];
	return fs.readdirSync(dir, { withFileTypes: true })
		.filter((entry) => entry.isFile() && entry.name.endsWith(".md"))
		.map((entry) => entry.name.replace(/\.md$/, ""));
}

function matchesDomain(text: string, domain: string): boolean {
	const lower = text.toLowerCase();
	const candidates = [domain.toLowerCase(), domain.toLowerCase().replace(/-/g, " ")]
		.filter((value, index, arr) => value.length > 0 && arr.indexOf(value) === index);
	return candidates.some((candidate) => new RegExp(`(^|[^a-z0-9])${escapeRegex(candidate)}([^a-z0-9]|$)`, "i").test(lower));
}

function detectTopics(text: string): string[] {
	const lower = text.toLowerCase();
	return TOPIC_RULES
		.filter((rule) => rule.terms.some((term) => lower.includes(term)))
		.map((rule) => rule.topic);
}

function looksLikeSnippet(text: string): boolean {
	return /(invoke-|get-|set-|select\s+|update\s+|delete\s+from|jj\s+|\.ps1|\{\s*"|```|\bdbo\.)/i.test(text);
}

function formatItem(item: InboxItem): string {
	const rel = `${path.basename(item.file)}:${item.line}`;
	return `${rel} ${truncate(item.text, 180)}`;
}

function addMapItem(map: Map<string, InboxItem[]>, key: string, item: InboxItem): void {
	const existing = map.get(key) ?? [];
	existing.push(item);
	map.set(key, existing);
}

function headingLevel(line: string): number | null {
	const match = line.trim().match(/^(#+)\s+/);
	return match ? match[1].length : null;
}

function findSectionEnd(lines: string[], startIdx: number, level: number): number {
	for (let i = startIdx + 1; i < lines.length; i++) {
		const current = headingLevel(lines[i]);
		if (current !== null && current <= level) return i;
	}
	return lines.length;
}

function trimBlankBefore(lines: string[], index: number, floor: number): number {
	let result = index;
	while (result > floor && lines[result - 1].trim() === "") result--;
	return result;
}

function formatDate(d: Date): string {
	const pad = (value: number): string => value.toString().padStart(2, "0");
	return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function formatTime(d: Date): string {
	const pad = (value: number): string => value.toString().padStart(2, "0");
	return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function truncate(text: string, max: number): string {
	return text.length <= max ? text : `${text.slice(0, max - 3)}...`;
}

function limitReport(text: string): string {
	const maxChars = 12000;
	if (text.length <= maxChars) return text;
	return `${text.slice(0, maxChars)}\n\n[truncated; narrow the window with --days, --weeks, or --current-week]`;
}

function escapeRegex(value: string): string {
	return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
