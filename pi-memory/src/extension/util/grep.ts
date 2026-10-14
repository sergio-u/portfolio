// In-process recursive grep over markdown files. Used by /recall (Phase
// 2 grep mode) and by the memory_search tool. Phase 3 adds AnythingLLM
// semantic search alongside this.

import * as fs from "node:fs";
import * as path from "node:path";

export interface GrepHit {
	file: string;
	line: number;
	snippet: string;
}

export function grepMarkdown(root: string, query: string, limit = 50): GrepHit[] {
	if (!fs.existsSync(root)) return [];
	const hits: GrepHit[] = [];
	const q = query.toLowerCase();
	const walk = (dir: string): void => {
		if (hits.length >= limit) return;
		for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
			if (hits.length >= limit) return;
			const full = path.join(dir, entry.name);
			if (entry.isDirectory()) {
				if (entry.name === "archive" || entry.name.startsWith(".")) continue;
				walk(full);
			} else if (entry.isFile() && full.endsWith(".md")) {
				const lines = fs.readFileSync(full, "utf8").split("\n");
				for (let i = 0; i < lines.length; i++) {
					if (lines[i].toLowerCase().includes(q)) {
						hits.push({ file: full, line: i + 1, snippet: truncateSnippet(lines[i]) });
						if (hits.length >= limit) return;
					}
				}
			}
		}
	};
	walk(root);
	return hits;
}

function truncateSnippet(text: string, maxChars = 240): string {
	return text.length > maxChars ? `${text.slice(0, maxChars - 3)}...` : text;
}
