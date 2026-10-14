// Path utilities: vault root resolution, ~/ expansion, week-of-year helpers.

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { type EffectiveConfig } from "../config/types.ts";

/**
 * Expand a leading `~` to the user's home directory. Returns the path
 * unchanged if it doesn't start with `~`.
 */
export function expandTilde(p: string): string {
	if (p === "~") return os.homedir();
	if (p.startsWith("~/")) return path.join(os.homedir(), p.slice(2));
	return p;
}

/**
 * Absolute path to the AI subfolder of the vault.
 * E.g. /Users/me/.../Notebook/2026-H1/80_AI
 */
export function aiRoot(config: EffectiveConfig): string {
	return path.join(expandTilde(config.vault.root), config.vault.ai_folder);
}

/**
 * Absolute path to the weekly-notes folder of the vault.
 */
export function weeklyRoot(config: EffectiveConfig): string {
	return path.join(expandTilde(config.vault.root), config.vault.weekly_folder);
}

/**
 * Absolute path to a project's folder under 80_AI/projects/.
 */
export function projectDir(config: EffectiveConfig, projectName: string): string {
	return path.join(aiRoot(config), "projects", projectName);
}

/**
 * Absolute path to a domain file: 80_AI/domains/<tag>.md
 */
export function domainFile(config: EffectiveConfig, tag: string): string {
	return path.join(aiRoot(config), "domains", `${tag}.md`);
}

/**
 * Compute the current weekly note filename for the configured strftime
 * pattern. Only the patterns we actually use are supported:
 *   %Y → 4-digit year
 *   %V → ISO 8601 week number (01-53), Monday start
 *   %m → 2-digit month
 *   %d → 2-digit day-of-month
 */
export function weeklyFilename(config: EffectiveConfig, now: Date = new Date()): string {
	const pattern = config.vault.weekly_filename;
	const year = now.getUTCFullYear().toString().padStart(4, "0");
	const month = (now.getUTCMonth() + 1).toString().padStart(2, "0");
	const day = now.getUTCDate().toString().padStart(2, "0");
	const isoWeek = isoWeekNumber(now).toString().padStart(2, "0");
	const base = pattern
		.replace(/%Y/g, year)
		.replace(/%V/g, isoWeek)
		.replace(/%m/g, month)
		.replace(/%d/g, day);
	return base.endsWith(".md") ? base : `${base}.md`;
}

/**
 * Absolute path to this week's weekly note.
 */
export function currentWeeklyFile(config: EffectiveConfig, now: Date = new Date()): string {
	return path.join(weeklyRoot(config), weeklyFilename(config, now));
}

export function resolveManagedMarkdownPath(config: EffectiveConfig, filePath: string): string {
	const expanded = expandTilde(filePath);
	if (!path.isAbsolute(expanded)) {
		throw new Error(`memory path must be absolute: ${filePath}`);
	}
	if (!expanded.endsWith(".md")) {
		throw new Error(`memory path must point to a markdown file: ${filePath}`);
	}

	const target = path.resolve(expanded);
	const vaultRoot = path.resolve(expandTilde(config.vault.root));
	const roots = [path.resolve(aiRoot(config)), path.resolve(weeklyRoot(config))];
	for (const root of roots) {
		if (!isPathInside(root, vaultRoot)) {
			throw new Error(`managed memory root escapes vault.root: ${root}`);
		}
	}
	const matchedRoot = roots.find((root) => isPathInside(target, root));
	if (!matchedRoot) {
		throw new Error(`memory path must stay under ${roots.join(" or ")}: ${filePath}`);
	}

	fs.mkdirSync(matchedRoot, { recursive: true });
	const realRoot = fs.realpathSync.native(matchedRoot);
	ensureRealAncestorInside(target, realRoot);
	if (fs.existsSync(target)) {
		const realTarget = fs.realpathSync.native(target);
		if (!isPathInside(realTarget, realRoot)) {
			throw new Error(`memory path resolves outside managed roots: ${filePath}`);
		}
	}
	return target;
}

export function assertSafePathSegment(value: string, label: string): string {
	const trimmed = value.trim();
	if (
		trimmed.length === 0 ||
		trimmed === "." ||
		trimmed === ".." ||
		trimmed.includes("/") ||
		trimmed.includes("\\") ||
		trimmed.includes("\0")
	) {
		throw new Error(`invalid ${label} name: ${value}`);
	}
	return trimmed;
}

function ensureRealAncestorInside(target: string, realRoot: string): void {
	let ancestor = path.dirname(target);
	while (!fs.existsSync(ancestor)) {
		const parent = path.dirname(ancestor);
		if (parent === ancestor) break;
		ancestor = parent;
	}
	const realAncestor = fs.realpathSync.native(ancestor);
	if (!isPathInside(realAncestor, realRoot)) {
		throw new Error(`memory path parent resolves outside managed root: ${target}`);
	}
}

function isPathInside(child: string, parent: string): boolean {
	const rel = path.relative(parent, child);
	return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel));
}

/**
 * ISO 8601 week number (Monday-start). Standard algorithm.
 */
function isoWeekNumber(d: Date): number {
	const target = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
	const dayNum = (target.getUTCDay() + 6) % 7; // Mon=0..Sun=6
	target.setUTCDate(target.getUTCDate() - dayNum + 3); // Thursday in current week
	const firstThursday = new Date(Date.UTC(target.getUTCFullYear(), 0, 4));
	const firstDayNum = (firstThursday.getUTCDay() + 6) % 7;
	firstThursday.setUTCDate(firstThursday.getUTCDate() - firstDayNum + 3);
	const diff = target.getTime() - firstThursday.getTime();
	return 1 + Math.round(diff / (7 * 24 * 60 * 60 * 1000));
}
