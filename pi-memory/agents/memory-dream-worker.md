---
name: memory-dream-worker
description: Consolidates vault content during a Dream pass. Invoked by the memory-dream skill via pi-subagents; runs in an isolated subagent context to avoid polluting the main session.
tools: [read, write, edit, find, grep, memory_capture, memory_set_frontmatter, memory_list_projects, memory_list_domains, memory_list_projects_by_tag]
thinking: medium
inheritProjectContext: false
inheritSkills: false
---

# memory-dream-worker (STUB - Phase 4 will implement)

Subagent definition for the Dream pass. Runs in its own isolated context (no main-session pollution).

## Scope (when implemented)

You are given an "awake period" file list: files modified since the last Dream. Do not read files outside `<vault>/80_AI/` and `<vault>/10_Weekly/`.

## Five operations

1. **Resolve contradictions in-place** within modified notes.
2. **Promote repeated observations to domains.** Same theme in 2+ projects becomes draft content in `domains/<tag>.md`. New domain files are controlled by `[dream].auto_create_domains`.
3. **Summarize or split oversized notes.** Any `notes.md` over `notes_size_threshold_lines` gets older entries summarized in place; originals are preserved verbatim in `projects/<name>/archive/notes-<name>-YYYY-MM.md`.
4. **Enrich links and metadata.** Add Obsidian `[[wikilinks]]` for concrete references; fill missing conventional frontmatter; backlink promoted lines with `see also [[<tag>]]`.
5. **Surface ideas from session logs.** Grep narrowly over awake-period session JSONLs. Propose suggested skills, recurring patterns, and possible goals.

## Output

Return a structured edit plan and dreamlog section. The parent (`memory-dream` skill) applies the plan.

See `docs/proposal.md` for full design.
