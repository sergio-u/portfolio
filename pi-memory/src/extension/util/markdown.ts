// Markdown file helpers used by both the tool registry (memory_capture,
// memory_set_frontmatter) and the slash command handlers (/note, etc.).
//
// Kept narrow on purpose: append-to-EOF, append-to-section, set-single-
// frontmatter-field, ensure-file-exists. Anything richer should grow its
// own module.

import * as fs from "node:fs";
import * as path from "node:path";

export function ensureFileExists(file: string): void {
	if (!fs.existsSync(file)) {
		fs.mkdirSync(path.dirname(file), { recursive: true });
		fs.writeFileSync(file, "", "utf8");
	}
}

export function appendToFile(file: string, line: string): void {
	ensureFileExists(file);
	let existing = fs.readFileSync(file, "utf8");
	if (existing.length > 0 && !existing.endsWith("\n")) existing += "\n";
	fs.writeFileSync(file, existing + line + "\n", "utf8");
}

/**
 * Append `line` at the end of `section` (e.g. "## Log") in `file`. If
 * the section doesn't exist, it's created at the end of the file.
 */
export function appendToSection(file: string, section: string, line: string): void {
	ensureFileExists(file);
	const text = fs.readFileSync(file, "utf8");
	const lines = text.split("\n");
	const headerIdx = lines.findIndex((l) => l.trim() === section.trim());
	if (headerIdx === -1) {
		const sep = text.length > 0 && !text.endsWith("\n") ? "\n" : "";
		fs.writeFileSync(file, text + sep + "\n" + section + "\n\n" + line + "\n", "utf8");
		return;
	}
	const headerLevel = section.match(/^#+/)?.[0]?.length ?? 2;
	let insertAt = lines.length;
	for (let i = headerIdx + 1; i < lines.length; i++) {
		const m = lines[i].match(/^(#+)\s/);
		if (m && m[1].length <= headerLevel) {
			insertAt = i;
			break;
		}
	}
	let cut = insertAt;
	while (cut > headerIdx + 1 && lines[cut - 1].trim() === "") cut--;
	lines.splice(cut, 0, line);
	fs.writeFileSync(file, lines.join("\n"), "utf8");
}

export function setFrontmatterField(
	file: string,
	key: string,
	value: string | number | boolean | string[],
): void {
	ensureFileExists(file);
	const text = fs.readFileSync(file, "utf8");
	const valueStr = formatYamlValue(value);
	const lines = text.split("\n");
	if (lines[0] === "---") {
		let endIdx = -1;
		for (let i = 1; i < lines.length; i++) {
			if (lines[i] === "---") { endIdx = i; break; }
		}
		if (endIdx === -1) {
			prependFrontmatter(file, key, valueStr, text);
			return;
		}
		const keyIdx = lines.findIndex(
			(l, i) => i > 0 && i < endIdx && l.replace(/\s+/g, "").startsWith(`${key}:`),
		);
		if (keyIdx === -1) {
			lines.splice(endIdx, 0, `${key}: ${valueStr}`);
		} else {
			lines[keyIdx] = `${key}: ${valueStr}`;
		}
		fs.writeFileSync(file, lines.join("\n"), "utf8");
	} else {
		prependFrontmatter(file, key, valueStr, text);
	}
}

function prependFrontmatter(file: string, key: string, valueStr: string, body: string): void {
	const fm = `---\n${key}: ${valueStr}\n---\n`;
	fs.writeFileSync(file, fm + body, "utf8");
}

function formatYamlValue(v: string | number | boolean | string[]): string {
	if (Array.isArray(v)) return `[${v.map((x) => JSON.stringify(x)).join(", ")}]`;
	if (typeof v === "string") return v.includes(" ") || v.includes(":") ? JSON.stringify(v) : v;
	return String(v);
}

/**
 * Format a timestamp in the form used by all our capture markers:
 *   YYYY-MM-DD HH:MM  (local time)
 */
export function fmtTimestamp(d: Date = new Date()): string {
	const pad = (n: number) => n.toString().padStart(2, "0");
	return (
		`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
		`${pad(d.getHours())}:${pad(d.getMinutes())}`
	);
}
