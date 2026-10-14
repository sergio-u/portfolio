// Helpers for creating project and plan markdown scaffolds.

import * as fs from "node:fs";
import * as path from "node:path";
import { withFileMutationQueue } from "@earendil-works/pi-coding-agent";
import type { EffectiveConfig } from "../config/types.ts";
import { assertSafePathSegment, projectDir, resolveManagedMarkdownPath } from "./paths.ts";

export async function ensureProjectScaffold(
	config: EffectiveConfig,
	projectName: string,
	tags: string[] = [],
): Promise<void> {
	const safeProject = assertSafePathSegment(projectName, "project");
	const dir = projectDir(config, safeProject);
	const projectMd = resolveManagedMarkdownPath(config, path.join(dir, "project.md"));
	const notesMd = resolveManagedMarkdownPath(config, path.join(dir, "notes.md"));
	await withFileMutationQueue(projectMd, async () => {
		if (!fs.existsSync(projectMd)) {
			fs.mkdirSync(path.dirname(projectMd), { recursive: true });
			fs.writeFileSync(
				projectMd,
				`---\ntags: ${formatInlineStringArray(tags)}\ndescription: ""\n---\n\n# ${safeProject}\n\nProject created by pi-memory.\n`,
				"utf8",
			);
		}
	});
	await withFileMutationQueue(notesMd, async () => {
		if (!fs.existsSync(notesMd)) {
			fs.mkdirSync(path.dirname(notesMd), { recursive: true });
			fs.writeFileSync(notesMd, "", "utf8");
		}
	});
}

export async function ensurePlanScaffold(
	config: EffectiveConfig,
	projectName: string,
	planName: string,
): Promise<void> {
	const safeProject = assertSafePathSegment(projectName, "project");
	const safePlan = assertSafePathSegment(planName, "plan");
	const file = resolveManagedMarkdownPath(config, path.join(projectDir(config, safeProject), "plans", safePlan, "plan.md"));
	await withFileMutationQueue(file, async () => {
		if (!fs.existsSync(file)) {
			fs.mkdirSync(path.dirname(file), { recursive: true });
			fs.writeFileSync(
				file,
				`---\nstatus: open\n---\n\n# ${safePlan}\n\n## Goal\n\n\n## Log\n\n`,
				"utf8",
			);
		}
	});
}

function formatInlineStringArray(values: string[]): string {
	return `[${values.map((value) => value.trim()).filter(isSafeInlineString).map((value) => JSON.stringify(value)).join(", ")}]`;
}

function isSafeInlineString(value: string): boolean {
	return (
		value.length > 0 &&
		value !== "." &&
		value !== ".." &&
		!value.includes("/") &&
		!value.includes("\\") &&
		!value.includes("\0")
	);
}
