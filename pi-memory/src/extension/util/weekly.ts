// Helpers for weekly memory inbox files.

import * as fs from "node:fs";
import * as path from "node:path";
import type { EffectiveConfig } from "../config/types.ts";
import { expandTilde, weeklyRoot } from "./paths.ts";

const WEEKLY_TEMPLATE_FALLBACK = (heading: string): string =>
	`# Weekly Note\n\n${heading}\n\n`;

/**
 * Create a weekly note from the configured template or a minimal stub.
 */
export function ensureWeeklyNote(config: EffectiveConfig, weeklyPath: string): void {
	if (fs.existsSync(weeklyPath)) return;
	fs.mkdirSync(weeklyRoot(config), { recursive: true });
	const templateRel = config.vault.weekly_template;
	if (templateRel) {
		const templateAbs = path.join(expandTilde(config.vault.root), templateRel);
		if (fs.existsSync(templateAbs)) {
			fs.copyFileSync(templateAbs, weeklyPath);
			return;
		}
	}
	fs.writeFileSync(weeklyPath, WEEKLY_TEMPLATE_FALLBACK(config.vault.weekly_inbox), "utf8");
}
