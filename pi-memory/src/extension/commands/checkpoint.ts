// /checkpoint [--all] — manual checkpoint fallback.
//
// The full LLM-driven workflow lives in skills/memory-checkpoint and
// requires a skill-invocation bridge that isn't yet wired (see Phase 3
// notes). For now `/checkpoint` does deterministic work:
//
//   1. Resolve the structural target (plan > project notes > weekly inbox).
//   2. Write a single [manual YYYY-MM-DD HH:MM] line to that target so
//      the user has a session-segment boundary they can later grep.
//   3. Advance the memory-checkpoint-marker so subsequent automatic
//      checkpoint bookkeeping knows to start from this point.
//   4. Report what happened via ctx.ui.notify.
//
// Flags:
//   --all   ignore any prior marker and treat the entire session as the
//           segment of interest. (Has no effect on the deterministic
//           path today, but is recorded in the marker's mode field so
//           the future LLM bridge can pick it up.)

import * as fs from "node:fs";
import * as path from "node:path";
import { withFileMutationQueue, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { tryLoadEffectiveConfig } from "../config/loader.ts";
import { readSentinel } from "../sentinel/reader.ts";
import { STATE_KEYS, type CheckpointMarker } from "../util/session-state.ts";
import { appendToFile, appendToSection, fmtTimestamp } from "../util/markdown.ts";
import { currentWeeklyFile, projectDir, resolveManagedMarkdownPath, weeklyRoot } from "../util/paths.ts";

export function registerCheckpoint(pi: ExtensionAPI): void {
	pi.registerCommand("checkpoint", {
		description:
			"Manually mark a session-segment boundary. Writes a single [manual YYYY-MM-DD HH:MM] line to the current target. Pass --all to record a from-session-start scope hint for future LLM-driven capture.",
		handler: async (args, ctx) => {
			const loaded = tryLoadEffectiveConfig(ctx.cwd);
			if (!loaded.ok) {
				ctx.ui.notify(loaded.message);
				return;
			}
			const config = loaded.config;
			const all = args.split(/\s+/).includes("--all");

			const sentinel = readSentinel(ctx.cwd);
			const projectName = sentinel?.state.projects[0];
			const planPath = sentinel?.state.plan;
			const line = `- [manual ${fmtTimestamp()}] checkpoint${all ? " (--all)" : ""}.`;

			let targetFile: string;
			let targetSection: string | undefined;
			let label: string;
			let ensureWeekly = false;

			if (projectName && planPath) {
				targetFile = path.join(projectDir(config, projectName), planPath, "plan.md");
				targetSection = "## Log";
				label = `plan ${planPath}`;
			} else if (projectName) {
				targetFile = path.join(projectDir(config, projectName), "notes.md");
				targetSection = undefined;
				label = `project ${projectName}`;
			} else {
				targetFile = currentWeeklyFile(config);
				targetSection = config.vault.weekly_inbox;
				label = "weekly inbox";
				ensureWeekly = true;
			}

			targetFile = resolveManagedMarkdownPath(config, targetFile);
			await withFileMutationQueue(targetFile, async () => {
				if (ensureWeekly && !fs.existsSync(targetFile)) {
					fs.mkdirSync(weeklyRoot(config), { recursive: true });
					fs.writeFileSync(targetFile, `# Weekly Note\n\n${config.vault.weekly_inbox}\n\n`, "utf8");
				}
				if (targetSection) {
					appendToSection(targetFile, targetSection, line);
				} else {
					appendToFile(targetFile, line);
				}
			});

			// Advance the marker. The mode field records whether --all was
			// passed so a future LLM-driven extraction step can pick up the
			// right segment window.
			const latestId = ctx.sessionManager.getLeafId() ?? "";
			const marker: CheckpointMarker = {
				entry_id: all ? "" : latestId,
				ts: new Date().toISOString(),
				mode: "manual",
			};
			pi.appendEntry(STATE_KEYS.CHECKPOINT_MARKER, marker);

			ctx.ui.notify(`checkpoint marked under ${label} -> ${targetFile}`);
		},
	});
}
