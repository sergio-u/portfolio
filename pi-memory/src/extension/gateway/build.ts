// Memory Gateway content builders.
//
// Two depths (per proposal §7):
//   buildBasicBlock   — ~100-200 tokens; metadata only. Auto-loaded at session_start.
//   buildFullSlice    — ~5k tokens; full project/plan/notes/domains content.
//                       Loaded on demand via /set-context.

import * as fs from "node:fs";
import * as path from "node:path";
import { type EffectiveConfig } from "../config/types.ts";
import { aiRoot, projectDir, domainFile } from "../util/paths.ts";

export interface BasicBlockInput {
	config: EffectiveConfig;
	repo: string;
	now?: Date;
}

export interface FullSliceInput extends BasicBlockInput {
	notesTailLines: number;
	tokenBudget: number;
}

/**
 * Build the basic-depth Memory Gateway block: repo, project, plan,
 * domain tags, last-dream status. Pure metadata --
 * no vault content is read for content; only filesystem stats + frontmatter.
 */
export function buildBasicBlock(input: BasicBlockInput): string {
	const { config, repo } = input;
	const projectName = config.state.projects[0];
	const planPath = config.state.plan;
	const lines: string[] = [];
	lines.push("## Memory state (basic -- run /set-context for full)");
	lines.push("");

	if (!projectName) {
		lines.push(`Repo: ${repo}   Project: (none)   Plan: (none)`);
		lines.push(`Captures route to ${config.vault.weekly_folder}/<this-week>.md ${config.vault.weekly_inbox}.`);
	} else {
		const headerParts = [`Repo: ${repo}`, `Project: ${projectName}`];
		if (planPath) headerParts.push(`Plan: ${stripPlanPath(planPath)}`);
		lines.push(headerParts.join("   "));

		const domains = readActiveDomains(config, projectName, repo)
		if (domains.length > 0) {
			lines.push(`Domains: ${domains.join(", ")}`);
		}
	}

	const dream = describeDreamStatus(config);
	if (dream) lines.push(dream);

	return lines.join("\n");
}

/**
 * Build the full-depth Memory Gateway slice — everything in the basic
 * block plus full project.md, recent notes.md tail, full plan.md (if
 * any), and full domains/<tag>.md for each tagged domain. Token-budgeted.
 */
export function buildFullSlice(input: FullSliceInput): string {
	const { config, repo, notesTailLines, tokenBudget } = input;
	const projectName = config.state.projects[0];
	const sections: string[] = [];

	// Lead with the basic block -- repo/project/plan/dream -- so the
	// LLM sees the orientation header first.
	sections.push(buildBasicBlock(input));

	if (!projectName) {
		sections.push("\nNo active project; nothing further to load. Use /set-context <name> to enter a project.");
		return sections.join("\n");
	}

	const pDir = projectDir(config, projectName);

	// project.md (full)
	const projectMd = path.join(pDir, "project.md");
	if (fs.existsSync(projectMd)) {
		sections.push(`\n## project.md\n\n${fs.readFileSync(projectMd, "utf8").trim()}`);
	}

	// notes.md (tail)
	const notesMd = path.join(pDir, "notes.md");
	if (fs.existsSync(notesMd)) {
		const allLines = fs.readFileSync(notesMd, "utf8").split("\n");
		const tail = allLines.slice(-notesTailLines).join("\n").trim();
		if (tail.length > 0) {
			sections.push(`\n## notes.md (last ${notesTailLines} lines)\n\n${tail}`);
		}
	}

	// active plan
	const planPath = config.state.plan;
	if (planPath) {
		const planMd = path.join(pDir, planPath, "plan.md");
		if (fs.existsSync(planMd)) {
			sections.push(`\n## ${planPath}/plan.md\n\n${fs.readFileSync(planMd, "utf8").trim()}`);
		}
	}

	// domain files for each tag
	const domains = readActiveDomains(config, projectName, repo)
	for (const tag of domains) {
		const dFile = domainFile(config, tag);
		if (fs.existsSync(dFile)) {
			sections.push(`\n## domains/${tag}.md\n\n${fs.readFileSync(dFile, "utf8").trim()}`);
		}
	}

	const assembled = sections.join("\n");
	return enforceTokenBudget(assembled, tokenBudget);
}

// ----- helpers ---------------------------------------------------------------

function stripPlanPath(planPath: string): string {
	// Convert "plans/2026-05-21-foo" to "2026-05-21-foo" for the header line.
	if (planPath.startsWith("plans/")) return planPath.slice("plans/".length);
	return planPath;
}

function readActiveDomains(config: EffectiveConfig, projectName: string, repo: string): string[] {
	const domains = uniqueStrings([...config.state.domains, ...readProjectTags(config, projectName)])
		.filter(isSafeDomainName);
	const repoDomain = repo.trim();
	if (isSafeDomainName(repoDomain) && fs.existsSync(domainFile(config, repoDomain)) && !domains.includes(repoDomain)) {
		domains.push(repoDomain);
	}
	return domains;
}

function readProjectTags(config: EffectiveConfig, projectName: string): string[] {
	const projectMd = path.join(projectDir(config, projectName), "project.md");
	if (!fs.existsSync(projectMd)) return [];
	const text = fs.readFileSync(projectMd, "utf8");
	const fm = text.match(/^---\n([\s\S]*?)\n---/);
	if (!fm) return [];
	const tagsLine = fm[1].split("\n").find((l) => /^tags:/.test(l.trim()));
	if (!tagsLine) return [];
	const raw = tagsLine.replace(/^tags:\s*/, "").trim();
	if (raw.startsWith("[") && raw.endsWith("]")) {
		return raw.slice(1, -1)
			.split(",")
			.map((s) => s.trim().replace(/^['"]|['"]$/g, ""))
			.filter(Boolean);
	}
	// Block-style YAML is ignored for now.
	return [];
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

function uniqueStrings(values: string[]): string[] {
	const seen = new Set<string>();
	const result: string[] = [];
	for (const value of values) {
		const trimmed = value.trim();
		if (!trimmed || seen.has(trimmed)) continue;
		seen.add(trimmed);
		result.push(trimmed);
	}
	return result;
}

function describeDreamStatus(config: EffectiveConfig): string | null {
	const marker = path.join(aiRoot(config), ".last_dream.marker");
	if (!fs.existsSync(marker)) {
		return "Last dream: never (run /dream to baseline).";
	}
	const mtime = fs.statSync(marker).mtime;
	const days = Math.floor((Date.now() - mtime.getTime()) / (1000 * 60 * 60 * 24));
	const overdue = days >= config.dream.days_between ? " — overdue, run /dream" : "";
	return `Last dream: ${days}d ago${overdue}.`;
}

/**
 * Trim assembled content to fit roughly within the token budget.
 * Rough heuristic: 1 token ≈ 4 characters. Prefer head over tail
 * (project.md + plan first; notes truncate last).
 */
function enforceTokenBudget(text: string, tokenBudget: number): string {
	const charBudget = tokenBudget * 4;
	if (text.length <= charBudget) return text;
	return text.slice(0, charBudget) + "\n\n[...truncated to fit gateway token budget...]";
}
