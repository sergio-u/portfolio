// Sentinel reader — thin wrapper around the config loader's loadSentinel.
//
// Kept as a separate module so callers in commands/hooks have a clear
// "I'm reading per-repo state" intent at the import site, even though
// the implementation defers to the config layer.
//
// The extension is VCS-agnostic. From here, .memory/config.toml is just
// a file in the working tree — we don't care how it got there or whether
// it's tracked, committed, or branched.

import { loadSentinel } from "../config/loader.ts";
import { type SentinelConfig } from "../config/types.ts";

export function readSentinel(cwd: string): SentinelConfig | null {
	return loadSentinel(cwd);
}

/**
 * Resolve the repo name for display purposes:
 *   1. Sentinel [repo].name override, if set.
 *   2. Otherwise the cwd's basename.
 */
export function resolveRepoName(cwd: string, sentinel: SentinelConfig | null): string {
	const override = sentinel?.repo?.name;
	if (override && override.trim() !== "") {
		return override;
	}
	return basename(cwd);
}

function basename(p: string): string {
	const trimmed = p.replace(/\/+$/, "");
	const idx = trimmed.lastIndexOf("/");
	return idx >= 0 ? trimmed.slice(idx + 1) : trimmed;
}
