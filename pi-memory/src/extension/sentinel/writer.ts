// Sentinel writer — updates <cwd>/.memory/config.toml in the working tree.
//
// The extension is intentionally VCS-agnostic. It just writes the file;
// whether and how it gets committed/scrubbed/synced is the user's choice:
//
//   - jj users: commit it to a dedicated commit with description starting
//     "[memory]" and configure `git.private-commits` to keep it from being
//     pushed. Branch switches in jj swap the working tree automatically,
//     giving per-branch divergence for free.
//   - git users without jj: gitignore .memory/ to keep it local, or commit
//     it (and accept that it'll show up in git history).
//
// Either way, the extension does not invoke jj or git. The README spells
// out the recommended jj workflow as guidance, not requirement.

import * as fs from "node:fs";
import * as path from "node:path";
import { stringify as stringifyToml } from "smol-toml";
import { type SentinelConfig } from "../config/types.ts";
import { getSentinelBaseDir } from "../config/loader.ts";
import { readSentinel } from "./reader.ts";

const SENTINEL_DIR_NAME = ".memory";
const SENTINEL_FILE_NAME = "config.toml";

/**
 * Write the full sentinel config to <cwd>/.memory/config.toml. Creates
 * the .memory/ directory if absent.
 */
export function writeSentinel(cwd: string, sentinel: SentinelConfig): void {
	const dir = path.join(getSentinelBaseDir(cwd), SENTINEL_DIR_NAME);
	fs.mkdirSync(dir, { recursive: true });
	const filePath = path.join(dir, SENTINEL_FILE_NAME);
	const tomlText = stringifyToml(sentinel as unknown as Record<string, unknown>);
	fs.writeFileSync(filePath, tomlText, "utf8");
}

/**
 * Update specific state fields, leaving overrides + repo info as they
 * were. Reads current sentinel (if any), merges the patch, writes back.
 */
export function updateSentinelState(
	cwd: string,
	patch: Partial<SentinelConfig["state"]>,
): void {
	const existing = readSentinelOrEmpty(cwd);
	const next: SentinelConfig = {
		repo: existing.repo,
		overrides: existing.overrides,
		state: {
			...existing.state,
			...patch,
		},
	};
	writeSentinel(cwd, next);
}

/**
 * Clear the active project (and active plan). Used by `/set-context /`
 * and `/set-context ~`.
 */
export function clearSentinelState(cwd: string): void {
	updateSentinelState(cwd, { projects: [], plan: "", domains: [] });
}

function readSentinelOrEmpty(cwd: string): SentinelConfig {
	return readSentinel(cwd) ?? { repo: {}, state: { projects: [], plan: "", domains: [] }, overrides: {} };
}
