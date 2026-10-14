// /memory-doctor [target] -- print internal extension state for diagnostics.
//
// Subcommands:
//   state    -- sentinel state + resolved repo
//   gateway  -- current gateway entry (level + content + ts)
//   config   -- effective merged config + env-var presence
//   prompts  -- discovered skill paths + skill descriptions
//   tools    -- registered tool names + descriptions
//   dream    -- last-dream marker + days since + awake-period file count
//   domains  -- active domain drift diagnostics

import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { loadGlobalConfig, loadSentinel, tryLoadEffectiveConfig } from "../config/loader.ts";
import { readSentinel, resolveRepoName } from "../sentinel/reader.ts";
import { readGateway } from "../util/session-state.ts";
import { aiRoot, assertSafePathSegment, domainFile, projectDir } from "../util/paths.ts";

export function registerMemoryDoctor(pi: ExtensionAPI): void {
	pi.registerCommand("memory-doctor", {
		description: "Diagnostic state for pi-memory. Subcommands: state, domains, gateway, config, prompts, tools, dream.",
		handler: async (args, ctx) => {
			const target = args.trim().split(/\s+/)[0] || "state";
			switch (target) {
				case "state":
					return showState(ctx);
				case "domains":
					return showDomains(ctx);
				case "gateway":
					return showGateway(ctx);
				case "config":
					return showConfig(ctx);
				case "prompts":
					return showPrompts(ctx);
				case "tools":
					return showTools(pi, ctx);
				case "dream":
					return showDream(ctx);
				default:
					ctx.ui.notify(`/memory-doctor: unknown target '${target}'. Try: state, domains, gateway, config, prompts, tools, dream.`);
			}
		},
	});
}

function showState(ctx: ExtensionContext): void {
	const sentinel = readSentinel(ctx.cwd);
	const repo = resolveRepoName(ctx.cwd, sentinel);
	const lines = [
		`repo: ${repo}`,
		`active project: ${sentinel?.state.projects.join(", ") || "(none)"}`,
		`active plan:    ${sentinel?.state.plan || "(none)"}`,
		`active domains: ${sentinel?.state.domains.join(", ") || "(none)"}`,
		`cwd: ${ctx.cwd}`,
	];
	ctx.ui.notify(lines.join("\n"));
}

function showDomains(ctx: ExtensionContext): void {
	const loaded = tryLoadEffectiveConfig(ctx.cwd);
	if (!loaded.ok) {
		ctx.ui.notify(`/memory-doctor domains: ${loaded.message}`);
		return;
	}
	const config = loaded.config;
	const sentinel = readSentinel(ctx.cwd);
	const repo = resolveRepoName(ctx.cwd, sentinel);
	const projectName = sentinel?.state.projects[0] ?? null;
	const sentinelDomains = activeDomains(sentinel?.state.domains ?? []);
	const projectMd = projectName ? path.join(projectDir(config, projectName), "project.md") : null;
	const projectTags = projectMd ? readProjectTags(projectMd) : [];
	const repoDomain = safeOptionalSegment(repo, "repo");
	const repoDomainFile = repoDomain ? domainFile(config, repoDomain) : null;
	const repoDomainExists = repoDomainFile ? fs.existsSync(repoDomainFile) : false;
	const loadedDomains = uniqueStrings([
		...sentinelDomains,
		...projectTags,
		...(repoDomain && repoDomainExists ? [repoDomain] : []),
	]);
	const missingProjectTags = projectMd && fs.existsSync(projectMd)
		? sentinelDomains.filter((domain) => !projectTags.includes(domain))
		: [];
	const tagsNotInSentinel = projectTags.filter((domain) => !sentinelDomains.includes(domain));
	const missingDomainFiles = uniqueStrings([...sentinelDomains, ...projectTags])
		.filter((domain) => !fs.existsSync(domainFile(config, domain)));

	const lines = [
		`repo: ${repo}`,
		`project: ${projectName ?? "(none)"}`,
		`sentinel domains: ${formatList(sentinelDomains)}`,
		`project tags: ${formatList(projectTags)}`,
		`repo-as-domain: ${repoDomain ? `${repoDomain} (${repoDomainExists ? "exists, auto-loaded" : "missing"})` : "(invalid repo name)"}`,
		`gateway domains: ${formatList(loadedDomains)}`,
	];

	const drift: string[] = [];
	if (projectName && projectMd && !fs.existsSync(projectMd)) {
		drift.push(`project.md missing: ${projectMd}`);
	}
	if (missingProjectTags.length > 0) {
		drift.push(`in sentinel but not project tags: ${missingProjectTags.join(", ")}`);
	}
	if (tagsNotInSentinel.length > 0) {
		drift.push(`in project tags but not sentinel: ${tagsNotInSentinel.join(", ")}`);
	}
	if (missingDomainFiles.length > 0) {
		drift.push(`domain files missing: ${missingDomainFiles.map((domain) => domainFile(config, domain)).join(", ")}`);
	}
	if (repoDomain && !repoDomainExists) {
		drift.push(`repo domain file missing: ${repoDomainFile}`);
	}
	lines.push("", drift.length > 0 ? "drift:" : "drift: none");
	for (const item of drift) lines.push(`- ${item}`);
	ctx.ui.notify(lines.join("\n"));
}

function readProjectTags(projectMdPath: string): string[] {
	if (!fs.existsSync(projectMdPath)) return [];
	const text = fs.readFileSync(projectMdPath, "utf8");
	const fm = text.match(/^---\n([\s\S]*?)\n---/);
	if (!fm) return [];
	const tagsLine = fm[1].split("\n").find((line) => /^tags:/.test(line.trim()));
	if (!tagsLine) return [];
	const raw = tagsLine.replace(/^tags:\s*/, "").trim();
	if (!raw.startsWith("[") || !raw.endsWith("]")) return [];
	return activeDomains(raw.slice(1, -1).split(",").map((value) => value.trim().replace(/^['"]|['"]$/g, "")));
}

function activeDomains(values: string[]): string[] {
	const seen = new Set<string>();
	const result: string[] = [];
	for (const value of values) {
		const safe = safeOptionalSegment(value, "domain");
		if (!safe || seen.has(safe)) continue;
		seen.add(safe);
		result.push(safe);
	}
	return result;
}

function uniqueStrings(values: string[]): string[] {
	const seen = new Set<string>();
	const result: string[] = [];
	for (const value of values) {
		if (seen.has(value)) continue;
		seen.add(value);
		result.push(value);
	}
	return result;
}

function safeOptionalSegment(value: string, label: string): string | null {
	try {
		return assertSafePathSegment(value, label);
	} catch {
		return null;
	}
}

function formatList(values: string[]): string {
	return values.length > 0 ? values.join(", ") : "(none)";
}

function showGateway(ctx: ExtensionContext): void {
	const gw = readGateway(ctx);
	if (!gw) {
		ctx.ui.notify("/memory-doctor gateway: no gateway entry yet. Try /set-context.");
		return;
	}
	ctx.ui.notify(`level: ${gw.level}\nts: ${gw.ts}\n---\n${gw.content}`);
}

function showConfig(ctx: ExtensionContext): void {
	const loaded = tryLoadEffectiveConfig(ctx.cwd);
	if (!loaded.ok) {
		ctx.ui.notify(`/memory-doctor config: ${loaded.message}`);
		return;
	}
	const merged = loaded.config;
	const globalPresent = loadGlobalConfig() !== null ? "yes" : "no";
	const sentinelPresent = loadSentinel(ctx.cwd) !== null ? "yes" : "no";
	const effectiveHost = merged.anythingllm.host ? "set" : "(unset)";
	const effectiveKey = merged.anythingllm.api_key ? "set" : "(unset)";
	const envHost = process.env.ANYTHINGLLM_HOST ? "set" : "(unset)";
	const envKey = process.env.ANYTHINGLLM_API_KEY ? "set" : "(unset)";
	ctx.ui.notify(
		`source: global=${globalPresent} sentinel=${sentinelPresent}\n` +
			`vault.root: ${merged.vault.root}\n` +
			`vault.ai_folder: ${merged.vault.ai_folder}\n` +
			`vault.weekly_folder: ${merged.vault.weekly_folder}\n` +
			`note.smart_routing: ${merged.note.smart_routing}\n` +
			`dream.days_between: ${merged.dream.days_between}\n` +
			`dump.group_by_day: ${merged.dump.group_by_day}\n` +
			`organize.default_window_days: ${merged.organize.default_window_days}\n` +
			`organize.min_items_for_domain_suggestion: ${merged.organize.min_items_for_domain_suggestion}\n` +
			`anythingllm.workspace: ${merged.anythingllm.workspace}\n` +
			`anythingllm.default_mode: ${merged.anythingllm.default_mode}\n` +
			`anythingllm.host: ${effectiveHost}\n` +
			`anythingllm.api_key: ${effectiveKey}\n` +
			`env ANYTHINGLLM_HOST: ${envHost}\n` +
			`env ANYTHINGLLM_API_KEY: ${envKey}`,
	);
}

function showPrompts(ctx: ExtensionContext): void {
	// Show two views so the user can see the gate's effect at a glance:
	//   1. Skills shipped on disk under <pkg>/skills/.
	//   2. Whether each would be exposed by resources_discover under the
	//      current effective config (memory-note is gated on
	//      [note].smart_routing; all others always load).
	const skillsDir = findShippedSkillsDir();
	if (!skillsDir) {
		ctx.ui.notify("/memory-doctor prompts: could not locate shipped skills dir.");
		return;
	}
	const loaded = tryLoadEffectiveConfig(ctx.cwd);
	const smartRouting = loaded.ok ? loaded.config.note.smart_routing : true;
	const lines: string[] = [
		`skills dir: ${skillsDir}`,
		`[note].smart_routing: ${smartRouting} -> memory-note exposed: ${smartRouting ? "yes" : "no"}`,
	];
	for (const entry of fs.readdirSync(skillsDir, { withFileTypes: true })) {
		if (!entry.isDirectory()) continue;
		const skillMd = path.join(skillsDir, entry.name, "SKILL.md");
		if (!fs.existsSync(skillMd)) continue;
		const text = fs.readFileSync(skillMd, "utf8");
		const desc = text.match(/description:\s*\|?\s*([^\n]+)/)?.[1].trim() ?? "(no description)";
		const disabled = /disable-model-invocation:\s*true/.test(text);
		const exposed = isExposed(entry.name, disabled, smartRouting);
		const tag = disabled ? " [manual-only]" : exposed ? "" : " [GATED OFF]";
		lines.push(`  ${entry.name}${tag}: ${desc.slice(0, 120)}`);
	}
	ctx.ui.notify(lines.join("\n"));
}

function isExposed(skillName: string, _disabled: boolean, smartRouting: boolean): boolean {
	// Mirrors the gate in src/extension/index.ts resources_discover.
	// memory-note is the only skill gated by config; everything else is
	// always loaded. disable-model-invocation is orthogonal: those skills
	// are loaded (so /skill:name works) but PI hides their description
	// from the auto-discovery system prompt.
	if (skillName === "memory-note") return smartRouting;
	return true;
}

function showTools(pi: ExtensionAPI, ctx: ExtensionContext): void {
	const names = pi.getAllTools().map((t) => t.name).filter((n) => n.startsWith("memory_"));
	ctx.ui.notify(`registered memory_* tools (${names.length}):\n  ${names.join("\n  ")}`);
}

function showDream(ctx: ExtensionContext): void {
	const loaded = tryLoadEffectiveConfig(ctx.cwd);
	if (!loaded.ok) {
		ctx.ui.notify(`/memory-doctor dream: ${loaded.message}`);
		return;
	}
	const config = loaded.config;
	const marker = path.join(aiRoot(config), ".last_dream.marker");
	if (!fs.existsSync(marker)) {
		ctx.ui.notify(`no .last_dream.marker yet at ${marker}. First /dream will baseline it.`);
		return;
	}
	const mtime = fs.statSync(marker).mtime;
	const days = Math.floor((Date.now() - mtime.getTime()) / (1000 * 60 * 60 * 24));
	const overdue = days >= config.dream.days_between ? " -- OVERDUE" : "";
	ctx.ui.notify(
		`last dream: ${mtime.toISOString()}\n` +
			`days since: ${days}${overdue}\n` +
			`marker: ${marker}`,
	);
}

function findShippedSkillsDir(): string | null {
	// Walk up from this file's dir to find a sibling skills/ folder.
	// In the installed extension layout, this file lives at
	// ~/.pi/agent/extensions/memory/src/extension/commands/memory-doctor.ts (or .js)
	// and skills/ is at ~/.pi/agent/extensions/memory/skills.
	// During dev it'll be the same: <repo>/skills/.
	const here = new URL(import.meta.url).pathname;
	let dir = path.dirname(here);
	for (let i = 0; i < 6; i++) {
		const candidate = path.join(dir, "skills");
		if (fs.existsSync(candidate) && fs.statSync(candidate).isDirectory()) {
			return candidate;
		}
		const parent = path.dirname(dir);
		if (parent === dir) break;
		dir = parent;
	}
	return null;
}
