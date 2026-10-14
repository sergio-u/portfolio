---
name: upstream-skill-ownership
description: "Use when adopting upstream skills. Track native ownership."
version: 0.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [skills, upstream, provenance, maintenance]
---

# Upstream Skill Ownership

Keep third-party skill content upstream-owned and local behavioral policy separate. This is a review procedure, not an updater, hook, or scheduled task.

## When to Use

- Importing skills from another agent into an explicitly authorized Hermes profile.
- Choosing between native Hermes tracking and a separate package manager.

## Procedure

1. Load `hermes-agent` and its CLI reference. Retrieve the live official skills-system documentation with `web_extract`; verify installed CLI help through `terminal`.
2. Resolve the authorized profile home and explicitly scope every Hermes command to it. Read source-agent provenance locks without modifying source workspaces. Do not infer upstream ownership from a folder name.
3. Inspect the upstream skill directory, full SKILL.md, referenced files, agent manifests, and license. Separate generic skill documents from repository-level runtime extensions. Never run remote scripts or package lifecycle hooks merely to install Markdown.
4. Prefer `hermes skills inspect IDENTIFIER` and native `hermes skills install IDENTIFIER --category CATEGORY` when the source is supported. Bare GitHub-shaped identifiers can resolve through skills.sh; record the actual adapter rather than assuming `github`.
5. Review the full native scan before confirming installation. An install with stdin closed can stage, scan, then cancel at ordinary confirmation. A SAFE verdict can still contain MEDIUM findings: obey the user's warning threshold, not only the aggregate verdict. Do not strip flagged examples or use `--force` to evade a warning boundary.
6. After installation, use `hermes skills list`, `hermes skills check NAME`, and `hermes skills audit NAME`. Verify every installed file against the exact source revision and verify expected file counts programmatically. `skill_view` should load without unexpected setup requirements.
7. Keep local behavioral overlays outside upstream-owned directories. Do not rewrite frontmatter merely to enable automatic behavior; arrange explicit loading through separately authorized persona instructions.

## Maintenance

Use `terminal` for `hermes skills check NAME` and, after reviewing upstream changes, `hermes skills update NAME`. Re-audit after an update. Do not claim an actual upgrade was tested when the command only returned `No updates available`.

## Pitfalls

- Native state is profile-local under `skills/.hub/`; the manager owns its lock, audit log, quarantine, and caches. Never hand-edit them. If direct reads are denied, respect that boundary and use supported interfaces such as list/check/audit and `hermes skills snapshot export -`.
- Snapshot export records source identifiers and categories, not a complete immutable lock. Preserve the native scan's exact source revision and full content hash in implementation notes.
- A moving branch is useful for update checks; a pinned URL intentionally remains pinned. Record whether the install follows upstream or stays fixed.
- In inspected Hermes versions, update internally calls install with `force=True` to replace existing files. Review before updating; do not assume future caution findings necessarily prompt. Never use unattended updates under a no-warning policy.
- CLI success exit codes can accompany cancellation or errors. Verify filesystem and registry effects instead.
- A syntax skill does not choose a vault backend or authorize note access. A communication-style skill does not establish a medical diagnosis.

## Verification

Report exact paths, actual source adapter/identifier, observed revision and scan hash, update/check results, and any withheld install. Distinguish installation, discovery, and behavioral activation. Account for manager-generated artifacts and leave unrelated profiles/configuration untouched.
