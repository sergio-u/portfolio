// /note <text> — capture a knowledge fragment, deterministically.
//
// Routes by precedence:
//   1. Active plan (from sentinel)    -> plan.md "## Log"
//   2. Active project (from sentinel) -> project notes.md (EOF)
//   3. No active project              -> 10_Weekly/<this-week>.md "## Inbox"
//
// This is the deterministic capture path. The LLM-mediated, possibly
// multi-target path is exposed via the auto-invocable memory-note skill
// (skills/memory-note/SKILL.md) — it fires from natural conversation
// when the LLM notices something worth capturing. The two paths
// coexist: /note is what the user types when they want guaranteed
// capture; the skill is what the LLM uses when it spots capture moments
// organically. The skill is gated by [note].smart_routing in the
// effective config (see index.ts resources_discover).

import * as path from "node:path";
import { withFileMutationQueue, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { tryLoadEffectiveConfig } from "../config/loader.ts";
import { readSentinel } from "../sentinel/reader.ts";
import { appendToFile, appendToSection, fmtTimestamp } from "../util/markdown.ts";
import { currentWeeklyFile, projectDir, resolveManagedMarkdownPath } from "../util/paths.ts";
import { ensureWeeklyNote } from "../util/weekly.ts";

export function registerNote(pi: ExtensionAPI): void {
	pi.registerCommand("note", {
		description:
			"Capture a knowledge fragment. Routes by context: active plan -> active project notes -> weekly inbox.",
		handler: async (args, ctx) => {
			const text = args.trim();
			if (text.length === 0) {
				ctx.ui.notify("/note: provide a text argument.");
				return;
			}

			const loaded = tryLoadEffectiveConfig(ctx.cwd);
			if (!loaded.ok) {
				ctx.ui.notify(loaded.message);
				return;
			}
			const sentinel = readSentinel(ctx.cwd);
			const config = loaded.config;
			const line = `- [${fmtTimestamp()}] ${text}`;

			const projectName = sentinel?.state.projects[0];
			const planPath = sentinel?.state.plan;

			let target: { file: string; section?: string; label: string; ensureWeekly?: boolean };

			if (projectName && planPath) {
				const planMd = path.join(projectDir(config, projectName), planPath, "plan.md");
				target = { file: planMd, section: "## Log", label: `plan ${planPath}` };
			} else if (projectName) {
				const notesMd = path.join(projectDir(config, projectName), "notes.md");
				target = { file: notesMd, label: `project ${projectName}` };
			} else {
				const weekly = currentWeeklyFile(config);
				target = { file: weekly, section: config.vault.weekly_inbox, label: "weekly inbox", ensureWeekly: true };
			}

			target.file = resolveManagedMarkdownPath(config, target.file);
			await withFileMutationQueue(target.file, async () => {
				if (target.ensureWeekly) ensureWeeklyNote(config, target.file);
				if (target.section) {
					appendToSection(target.file, target.section, line);
				} else {
					appendToFile(target.file, line);
				}
			});

			ctx.ui.notify(`noted under ${target.label} -> ${target.file}`);
		},
	});
}
