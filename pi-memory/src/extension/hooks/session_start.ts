// session_start hook — loads config + sentinel, builds the basic Memory
// Gateway block, stashes it via pi.appendEntry. Cheap (no LLM cost,
// just filesystem stats); fires on every session, reload, fork, resume.

import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { tryLoadEffectiveConfig } from "../config/loader.ts";
import { readSentinel, resolveRepoName } from "../sentinel/reader.ts";
import { buildBasicBlock } from "../gateway/build.ts";
import { STATE_KEYS, type GatewayEntry } from "../util/session-state.ts";
import { aiRoot } from "../util/paths.ts";

export function registerSessionStart(pi: ExtensionAPI): void {
	pi.on("session_start", async (_event, ctx) => {
		const loaded = tryLoadEffectiveConfig(ctx.cwd);
		if (!loaded.ok) {
			// First-run / not configured. Notify the user once. We don't error
			// out — other commands work without config until the user copies
			// the example template or supplies [overrides.vault].root in the
			// per-repo sentinel.
			ctx.ui.notify(loaded.message);
			return;
		}

		const sentinel = readSentinel(ctx.cwd);
		const config = loaded.config;
		const repo = resolveRepoName(ctx.cwd, sentinel);
		const content = buildBasicBlock({ config, repo });

		const entry: GatewayEntry = {
			level: "basic",
			content,
			ts: new Date().toISOString(),
		};
		pi.appendEntry(STATE_KEYS.GATEWAY, entry);

		// Dream-overdue notification — soft hint, never auto-runs.
		const marker = path.join(aiRoot(config), ".last_dream.marker");
		if (fs.existsSync(marker) && config.dream.notify_on_overdue) {
			const days = Math.floor(
				(Date.now() - fs.statSync(marker).mtime.getTime()) / (1000 * 60 * 60 * 24),
			);
			if (days >= config.dream.days_between) {
				ctx.ui.notify(`pi-memory: memory hasn't been dreamed in ${days} days. Run /dream when ready.`);
			}
		}
	});
}
