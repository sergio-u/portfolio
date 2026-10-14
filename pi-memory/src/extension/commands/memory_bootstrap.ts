// /memory-bootstrap -- create missing markdown files for the active memory context.
//
// This is intentionally deterministic and lightweight: it only creates
// missing files from simple templates and replaces placeholders such as
// {{title}} / {{date}} plus obvious frontmatter arrays. It never rewrites
// existing files.

import * as fs from "node:fs";
import * as path from "node:path";
import { withFileMutationQueue, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { loadEffectiveConfig, tryLoadEffectiveConfig } from "../config/loader.ts";
import { readSentinel, resolveRepoName } from "../sentinel/reader.ts";
import {
	assertSafePathSegment,
	currentWeeklyFile,
	domainFile,
	expandTilde,
	projectDir,
	resolveManagedMarkdownPath,
} from "../util/paths.ts";

interface BootstrapTarget {
	file: string;
	templateName: string;
	title: string;
	kind: "project" | "notes" | "plan" | "domain" | "repo-domain" | "weekly";
	tags?: string[];
	repos?: string[];
}

export function registerMemoryBootstrap(pi: ExtensionAPI): void {
	pi.registerCommand("memory-bootstrap", {
		description:
			"Create missing markdown files for the active memory context: project, notes, plan, active domains, repo-domain, or weekly fallback. Existing files are never rewritten.",
		handler: async (args, ctx) => {
			const dryRun = args.split(/\s+/).includes("--dry-run");
			const loaded = tryLoadEffectiveConfig(ctx.cwd);
			if (!loaded.ok) {
				ctx.ui.notify(loaded.message);
				return;
			}

			const config = loaded.config;
			const sentinel = readSentinel(ctx.cwd);
			const repo = safeOptionalSegment(resolveRepoName(ctx.cwd, sentinel), "repo");
			const projectName = sentinel?.state.projects[0]
				? assertSafePathSegment(sentinel.state.projects[0], "project")
				: undefined;
			const planPath = sentinel?.state.plan ? normalizePlanPath(sentinel.state.plan) : "";
			const sentinelDomains = activeDomains(sentinel?.state.domains ?? []);
			const existingProjectTags = projectName
				? readProjectTags(path.join(projectDir(config, projectName), "project.md"))
				: [];
			const contextDomains = uniqueStrings([...sentinelDomains, ...existingProjectTags]);

			const targets: BootstrapTarget[] = [];
			if (projectName) {
				targets.push({
					file: path.join(projectDir(config, projectName), "project.md"),
					templateName: "Project.md",
					title: projectName,
					kind: "project",
					tags: contextDomains,
					repos: repo ? [repo] : [],
				});
				targets.push({
					file: path.join(projectDir(config, projectName), "notes.md"),
					templateName: "Notes.md",
					title: "notes",
					kind: "notes",
				});
				if (planPath) {
					const planName = stripPlanPath(planPath);
					targets.push({
						file: path.join(projectDir(config, projectName), planPath, "plan.md"),
						templateName: "Plan.md",
						title: planName,
						kind: "plan",
					});
				}
			} else {
				targets.push({
					file: currentWeeklyFile(config),
					templateName: "Weekly Memory Inbox.md",
					title: "Weekly Note",
					kind: "weekly",
				});
			}

			for (const domain of contextDomains) {
				targets.push({
					file: domainFile(config, domain),
					templateName: "Domain.md",
					title: domain,
					kind: "domain",
				});
			}
			if (repo) {
				targets.push({
					file: domainFile(config, repo),
					templateName: "Repo Domain.md",
					title: repo,
					kind: "repo-domain",
					tags: contextDomains.filter((domain) => domain !== repo),
				});
			}

			const created: string[] = [];
			const existing: string[] = [];
			for (const target of targets) {
				const file = resolveManagedMarkdownPath(config, target.file);
				if (fs.existsSync(file)) {
					existing.push(file);
					continue;
				}
				if (dryRun) {
					created.push(file);
					continue;
				}
				const content = renderTemplate(config, target);
				await withFileMutationQueue(file, async () => {
					if (fs.existsSync(file)) return;
					fs.mkdirSync(path.dirname(file), { recursive: true });
					fs.writeFileSync(file, content, "utf8");
				});
				created.push(file);
			}

			const mode = dryRun ? "would create" : "created";
			const lines = [
				`memory-bootstrap: ${mode} ${created.length} file(s); ${existing.length} already existed.`,
			];
			if (created.length > 0) lines.push("", ...created.map((file) => `+ ${file}`));
			ctx.ui.notify(lines.join("\n"));
		},
	});
}

function renderTemplate(config: ReturnType<typeof loadEffectiveConfig>, target: BootstrapTarget): string {
	if (target.kind === "notes") return "";
	const template = loadTemplate(config, target.templateName) ?? fallbackTemplate(target.kind);
	return template
		.replace(/\{\{title\}\}/g, target.title)
		.replace(/\{\{date\}\}/g, currentDate())
		.replace(/^tags:\s*\[\]/m, `tags: ${formatInlineStringArray(target.tags ?? [])}`)
		.replace(/^repos:\s*\[\]/m, `repos: ${formatInlineStringArray(target.repos ?? [])}`);
}

function loadTemplate(config: ReturnType<typeof loadEffectiveConfig>, templateName: string): string | null {
	const file = path.join(expandTilde(config.vault.root), "99_System", "Templates", "Memory", templateName);
	if (!fs.existsSync(file)) return null;
	return fs.readFileSync(file, "utf8");
}

function fallbackTemplate(kind: BootstrapTarget["kind"]): string {
	switch (kind) {
		case "project":
			return `---\ntags: []\ndescription: ""\nrepos: []\ncreated: "{{date}}"\n---\n\n# {{title}}\n\n## Overview\n\n\n## Decisions\n\n\n## Notes\n\n\n## Links\n\n`;
		case "plan":
			return `---\nstatus: open\ncreated: "{{date}}"\n---\n\n# {{title}}\n\n## Goal\n\n\n## Context\n\n\n## Success criteria\n\n- \n\n## Decisions\n\n\n## Log\n\n`;
		case "repo-domain":
			return `---\ntags: []\ndescription: ""\nkind: repo\ncreated: "{{date}}"\n---\n\n# {{title}}\n\n## Overview\n\n\n## Build and test\n\n\n## Local workflow\n\n\n## Architecture notes\n\n\n## Gotchas\n\n\n## Links\n\n`;
		case "weekly":
			return `# Weekly Note\n\n## Inbox\n\n\n## Memory review\n\n### Captures to route\n\n- \n\n### Follow-ups\n\n- \n\n`;
		case "domain":
		default:
			return `---\ntags: []\ndescription: ""\ncreated: "{{date}}"\n---\n\n# {{title}}\n\n## Overview\n\n\n## Patterns\n\n\n## Gotchas\n\n\n## Notes\n\n`;
	}
}

function readProjectTags(projectMd: string): string[] {
	if (!fs.existsSync(projectMd)) return [];
	const text = fs.readFileSync(projectMd, "utf8");
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
		const trimmed = safeOptionalSegment(value, "domain");
		if (!trimmed || seen.has(trimmed)) continue;
		seen.add(trimmed);
		result.push(trimmed);
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

function normalizePlanPath(planPath: string): string {
	const parts = planPath.split("/").map((part) => part.trim()).filter(Boolean);
	if (parts.length !== 2 || parts[0] !== "plans") {
		throw new Error(`invalid plan path: ${planPath}`);
	}
	return `plans/${assertSafePathSegment(parts[1], "plan")}`;
}

function stripPlanPath(planPath: string): string {
	return planPath.startsWith("plans/") ? planPath.slice("plans/".length) : planPath;
}

function formatInlineStringArray(values: string[]): string {
	return `[${values.map((value) => JSON.stringify(value)).join(", ")}]`;
}

function currentDate(): string {
	const now = new Date();
	const pad = (value: number): string => value.toString().padStart(2, "0");
	return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}
