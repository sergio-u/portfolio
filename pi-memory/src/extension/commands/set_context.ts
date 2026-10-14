// /set-context [<path>] -- navigate project / plan and load the
// full Memory Gateway. Updates the per-branch sentinel for project and
// active plan.
//
// Path syntax:
//   /set-context                       refresh-load the gateway for current state
//   /set-context project               set active project
//   /set-context project/plan          set project + plan
//   /set-context /                     clear sentinel, revert to basic gateway
//   /set-context ~                     same as /
//   /set-context ..                    drop one level (plan -> project -> none)

import { type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { tryLoadEffectiveConfig } from "../config/loader.ts";
import { readSentinel, resolveRepoName } from "../sentinel/reader.ts";
import { updateSentinelState, clearSentinelState } from "../sentinel/writer.ts";
import { buildFullSlice, buildBasicBlock } from "../gateway/build.ts";
import { STATE_KEYS, type GatewayEntry } from "../util/session-state.ts";
import { assertSafePathSegment } from "../util/paths.ts";
import { ensureProjectScaffold, ensurePlanScaffold } from "../util/scaffold.ts";

interface ParsedPath {
	project?: string;
	plan?: string;
	clear?: boolean;
	up?: boolean;
}

export function registerSetContext(pi: ExtensionAPI): void {
	pi.registerCommand("set-context", {
		description:
			"Navigate project / plan; loads the full Memory Gateway for the current state. Path: '<project>[/<plan>]', '..' to go up, '/' or '~' to clear.",
		handler: async (args, ctx) => {
			const arg = args.trim();
			const loaded = tryLoadEffectiveConfig(ctx.cwd);
			if (!loaded.ok) {
				ctx.ui.notify(loaded.message);
				return;
			}

			if (arg === "") {
				await loadFullGateway(pi, ctx.cwd);
				ctx.ui.notify("set-context: refreshed full gateway for current state.");
				return;
			}

			let parsed: ParsedPath;
			try {
				parsed = parsePath(arg);
			} catch (err) {
				const msg = err instanceof Error ? err.message : String(err);
				ctx.ui.notify(`/set-context: ${msg}`);
				return;
			}

			if (parsed.clear) {
				clearSentinelState(ctx.cwd);
				const sentinel = readSentinel(ctx.cwd);
				const refreshed = tryLoadEffectiveConfig(ctx.cwd);
				if (!refreshed.ok) {
					ctx.ui.notify(refreshed.message);
					return;
				}
				const repo = resolveRepoName(ctx.cwd, sentinel);
				const content = buildBasicBlock({ config: refreshed.config, repo });
				pi.appendEntry(STATE_KEYS.GATEWAY, { level: "basic", content, ts: now() });
				ctx.ui.notify("set-context: cleared. Captures route to weekly inbox.");
				return;
			}

			if (parsed.up) {
				const sentinelNow = readSentinel(ctx.cwd);
				let label: string;
				if (sentinelNow?.state.plan) {
					updateSentinelState(ctx.cwd, { plan: "" });
					label = `project ${sentinelNow.state.projects[0] ?? "(none)"}`;
				} else if (sentinelNow?.state.projects.length) {
					clearSentinelState(ctx.cwd);
					label = "no active project";
				} else {
					label = "no active context";
				}
				await loadFullGateway(pi, ctx.cwd);
				ctx.ui.notify(`set-context: up -> ${label}`);
				return;
			}

			if (!parsed.project) {
				ctx.ui.notify(`/set-context: invalid path "${arg}".`);
				return;
			}

			const config = loaded.config;
			await ensureProjectScaffold(config, parsed.project);
			const planPath = parsed.plan ? `plans/${parsed.plan}` : "";
			if (parsed.plan) {
				await ensurePlanScaffold(config, parsed.project, parsed.plan);
			}
			updateSentinelState(ctx.cwd, {
				projects: [parsed.project],
				plan: planPath,
			});

			await loadFullGateway(pi, ctx.cwd);
			const labelParts = [`project=${parsed.project}`];
			if (parsed.plan) labelParts.push(`plan=${parsed.plan}`);
			ctx.ui.notify(`set-context: ${labelParts.join(", ")}. Full gateway loaded.`);
		},
	});
}

async function loadFullGateway(pi: ExtensionAPI, cwd: string): Promise<void> {
	const loaded = tryLoadEffectiveConfig(cwd);
	if (!loaded.ok) return;
	const sentinel = readSentinel(cwd);
	const config = loaded.config;
	const repo = resolveRepoName(cwd, sentinel);
	const content = buildFullSlice({
		config,
		repo,
		notesTailLines: config.gateway.notes_tail_lines,
		tokenBudget: config.gateway.token_budget,
	});
	const entry: GatewayEntry = { level: "full", content, ts: now() };
	pi.appendEntry(STATE_KEYS.GATEWAY, entry);
}

function parsePath(arg: string): ParsedPath {
	if (arg === "/" || arg === "~") return { clear: true };
	if (arg === "..") return { up: true };
	const parts = arg.split("/").map((s) => s.trim()).filter(Boolean);
	if (parts.length > 2) throw new Error(`too many context path segments: "${arg}"`);
	return {
		project: parts[0] ? assertSafePathSegment(parts[0], "project") : undefined,
		plan: parts[1] ? assertSafePathSegment(parts[1], "plan") : undefined,
	};
}

function now(): string {
	return new Date().toISOString();
}
