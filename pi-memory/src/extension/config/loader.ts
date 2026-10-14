// Two-tier config loader: global (~/.pi/memory/config.toml) merged with
// per-branch sentinel overrides (<cwd>/.memory/config.toml).
//
// Either tier can be absent: if there's no global file, the sentinel can
// fully supply the effective config (handy for tests and per-repo
// isolation). The only hard requirement is that `vault.root` ends up
// non-empty after merging — that's the one field the rest of the
// extension can't function without.
//
// AnythingLLM host/API key can come from config TOML or from env vars.
// Env vars take precedence so users can keep secrets out of disk config
// when desired.

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { parse as parseToml } from "smol-toml";
import {
	DEFAULT_CONFIG,
	EMPTY_SENTINEL,
	type EffectiveConfig,
	type GlobalConfig,
	type SentinelConfig,
} from "./types.ts";

const GLOBAL_CONFIG_PATH = path.join(os.homedir(), ".pi", "memory", "config.toml");
const SENTINEL_RELATIVE_PATH = path.join(".memory", "config.toml");

/**
 * Load and parse the global config file. Returns `null` if the file does
 * not exist — that's fine; callers can still get a usable
 * `EffectiveConfig` if the sentinel supplies `vault.root` via
 * `[overrides.vault]`.
 */
export function loadGlobalConfig(): GlobalConfig | null {
	if (!fs.existsSync(GLOBAL_CONFIG_PATH)) {
		return null;
	}
	const raw = fs.readFileSync(GLOBAL_CONFIG_PATH, "utf8");
	const parsed = parseToml(raw) as unknown as Partial<GlobalConfig>;
	return deepMerge(DEFAULT_CONFIG, parsed) as GlobalConfig;
}

/**
 * Find the nearest per-repo sentinel by walking upward from cwd. This lets
 * pi be launched from a subdirectory while still using the repo-level
 * .memory/config.toml.
 */
export function findSentinelPath(cwd: string): string | null {
	const repoRoot = findNearestRepoRoot(cwd);
	let dir = path.resolve(cwd);
	for (;;) {
		const sentinelPath = path.join(dir, SENTINEL_RELATIVE_PATH);
		if (fs.existsSync(sentinelPath)) return sentinelPath;
		if (repoRoot && dir === repoRoot) return null;
		const parent = path.dirname(dir);
		if (parent === dir) return null;
		dir = parent;
	}
}

/**
 * Directory where a new sentinel should be written. Prefer an existing
 * sentinel location; otherwise use the nearest git/jj repo root, falling
 * back to cwd when no VCS marker is found.
 */
export function getSentinelBaseDir(cwd: string): string {
	const existing = findSentinelPath(cwd);
	if (existing) return path.dirname(path.dirname(existing));
	return findRepoRoot(cwd);
}

/**
 * Read the per-repo config from the nearest ancestor .memory/config.toml.
 * The extension is VCS-agnostic; this is just a filesystem read. Whether
 * the file is committed to jj, gitignored, or anything else, is the
 * user's choice.
 *
 * Returns `null` when no file exists (e.g. fresh repo, no project active).
 */
export function loadSentinel(cwd: string): SentinelConfig | null {
	const sentinelPath = findSentinelPath(cwd);
	if (!sentinelPath) {
		return null;
	}
	const raw = fs.readFileSync(sentinelPath, "utf8");
	const parsed = parseToml(raw) as unknown as Partial<SentinelConfig>;
	return {
		repo: parsed.repo ?? {},
		state: {
			projects: parsed.state?.projects ?? [],
			plan: parsed.state?.plan ?? "",
			domains: parsed.state?.domains ?? [],
		},
		overrides: parsed.overrides ?? {},
	};
}

function findRepoRoot(cwd: string): string {
	return findNearestRepoRoot(cwd) ?? path.resolve(cwd);
}

function findNearestRepoRoot(cwd: string): string | null {
	let dir = path.resolve(cwd);
	for (;;) {
		if (fs.existsSync(path.join(dir, ".git")) || fs.existsSync(path.join(dir, ".jj"))) {
			return dir;
		}
		const parent = path.dirname(dir);
		if (parent === dir) return null;
		dir = parent;
	}
}

/**
 * Merge a (possibly-null) global config with sentinel overrides + state.
 * When both are present, sentinel overrides win. When global is null we
 * fall back to `DEFAULT_CONFIG`; the sentinel is then responsible for
 * filling in `vault.root` if the result is to be functional.
 *
 * Env-var substitution for AnythingLLM credentials always runs last, so
 * the env vars work regardless of which tier supplied the rest of the
 * config.
 */
export function mergeConfig(
	global: GlobalConfig | null,
	sentinel: SentinelConfig | null,
): EffectiveConfig {
	const base = global ?? DEFAULT_CONFIG;
	const s = sentinel ?? EMPTY_SENTINEL;
	const overridden = deepMerge(base, s.overrides ?? {}) as GlobalConfig;
	const withEnv = applyEnvSubstitution(overridden);
	return {
		...withEnv,
		repo: s.repo,
		state: s.state,
	};
}

export type LoadResult =
	| { ok: true; config: EffectiveConfig }
	| { ok: false; message: string };

/**
 * Soft variant of `loadEffectiveConfig`: returns a discriminated result
 * instead of throwing. Use this from command handlers and hooks so the
 * missing-config UX is consistent (a `ctx.ui.notify` instead of a crash).
 */
export function tryLoadEffectiveConfig(cwd: string): LoadResult {
	const global = loadGlobalConfig();
	const sentinel = loadSentinel(cwd);
	const config = mergeConfig(global, sentinel);
	if (!config.vault.root || config.vault.root.trim() === "") {
		return {
			ok: false,
			message:
				"pi-memory: vault.root is unset. Either copy templates/config.example.toml to " +
				`${GLOBAL_CONFIG_PATH} and edit [vault].root, or set [overrides.vault].root in ` +
				`<repo>/.memory/config.toml.`,
		};
	}
	return { ok: true, config };
}

/**
 * Convenience: load + merge in one call. Throws when no source has
 * supplied `vault.root`. Prefer `tryLoadEffectiveConfig` in command
 * handlers; this throwing form is fine inside tool `execute()` bodies
 * where the agent loop will surface the message as a tool error.
 */
export function loadEffectiveConfig(cwd: string): EffectiveConfig {
	const result = tryLoadEffectiveConfig(cwd);
	if (!result.ok) {
		throw new Error(result.message);
	}
	return result.config;
}

/**
 * Apply AnythingLLM env-var overrides. TOML values are allowed, but env
 * vars win so shell/secret-manager configuration can override files.
 */
function applyEnvSubstitution(config: GlobalConfig): GlobalConfig {
	return {
		...config,
		anythingllm: {
			...config.anythingllm,
			host: process.env.ANYTHINGLLM_HOST ?? config.anythingllm.host,
			api_key: process.env.ANYTHINGLLM_API_KEY ?? config.anythingllm.api_key,
		},
	};
}

/**
 * Recursive deep merge that overlays the source on top of the target,
 * preserving the target's keys for any not present in source. Arrays are
 * REPLACED (not concatenated) by source — matches TOML override semantics.
 */
function deepMerge<T>(target: T, source: Partial<T>): T {
	if (!source || typeof source !== "object") {
		return target;
	}
	const result: Record<string, unknown> = { ...(target as Record<string, unknown>) };
	for (const key of Object.keys(source) as (keyof T)[]) {
		const sourceVal = (source as Record<string, unknown>)[key as string];
		const targetVal = (target as Record<string, unknown>)[key as string];
		if (sourceVal === undefined) continue;
		if (Array.isArray(sourceVal)) {
			result[key as string] = sourceVal;
		} else if (
			sourceVal !== null &&
			typeof sourceVal === "object" &&
			targetVal !== null &&
			typeof targetVal === "object" &&
			!Array.isArray(targetVal)
		) {
			result[key as string] = deepMerge(targetVal, sourceVal);
		} else {
			result[key as string] = sourceVal;
		}
	}
	return result as T;
}
