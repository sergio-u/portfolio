# Local overrides to bundled hermes-agent references

Upstream lines replaced or added locally (verified in this install). Prefer these over the bundled text when they conflict; recheck against live docs after updates.

## From references/background-systems.md

- **Single:** `delegate_task(tasks=[{"goal": "...", "context": "..."}])`.
- **Batch:** put independent tasks in that same tasks array; use the live schema's concurrency limit.
- **Background:** dispatch behavior is selected by the runtime; do not invent a `background` argument when the schema does not expose one. If the result says dispatched/background, finish independent work, then end the turn for completion delivery. Do not poll child transcripts or artifacts while waiting.
- **Version-sensitive behavior:** do not size jobs using an assumed universal three-minute hard limit. Current cron docs distinguish script timeout and agent inactivity budgets; inspect the installed scheduler and resolved cron settings before promising a bound. `.tick.lock` coordinates ticks and cron sessions default to `skip_memory=True`. Delivery continuation/mirroring depends on target eligibility and version; consult current docs. In a plain CLI, local/default-origin output does not notify the user in that CLI.

## From references/project-context-files.md

Hermes injects project-level instructions into the system prompt from project context files. Only one project context type wins, but that type can contribute a directory chain. Check the live context-file docs and installed `agent/prompt_builder.py` before relying on discovery details.
| `AGENTS.override.md` / `AGENTS.md` / `agents.md` | Inside Git: merged git-root-to-cwd chain; first nonempty filename wins per directory, override first. Outside Git: cwd only at startup. Subdirectory context can be discovered progressively. | Portable project guidance; use the override for personal per-directory rules |
- **Use `AGENTS.md`** for shared project instructions, but do not assume every harness has identical discovery semantics. Hermes merges the Git directory chain at startup and can discover subdirectory guidance progressively; outside Git, startup discovery checks cwd only.

## From references/troubleshooting.md

4. **Desktop/TUI sessions resolve toolsets from `platform_toolsets.cli`** (`tui_gateway/server.py` `_load_enabled_toolsets`) and only fold in surface toolsets (`desktop_ui`, `catalog`, `project`). Fix missing desktop tools under `cli`; a `platform_toolsets.desktop` entry is ignored. Check this in source before proposing a per-platform fix — there is one declaration, so no cli/desktop drift.
5. Plugin tools with a config `check_fn` (e.g. `a2a`, gated on `a2a_agents`/`platforms.a2a.enabled`) appear only in sessions started after the config exists (or after compaction) — start a new chat before debugging further. An update-time "unknown toolset 'a2a'" warning is cosmetic (validation runs before plugin discovery).
6. Verify config before claiming a tool is not enabled: grep `config.yaml` for the toolset and peer config; don't answer from stale memory.
### `Skill '' not found.` despite successful named skill loads

Inspect actual assistant tool-call records before changing skill configuration. If a populated call and a `{}` call share the SAME call ID, followed by success and an empty-name error, diagnose duplicate Responses stream assembly rather than a missing skill. Check whether other tools also have same-ID empty copies; do not print unrelated payloads or credentials while querying session records.

On the Copilot/codex_responses path, compare pending-call identity in `agent/codex_runtime.py`: an item announced under one ID and completed under another can leave a stale pending call, which terminal settlement executes again with `{}`. Reproduce with a credential-free synthetic event stream against the installed assembler; distinguish that witness from captured live SSE. Match both source and runtime evidence before concluding the same bug.

Upstream tracking to recheck live: issue #94707; fix PR #94708 (call-ID coalescing); related PR #111505 (rotating argument-event IDs/output-index correlation). Issue #96925 was closed as a duplicate, not as proof of a merged fix. Never promise `hermes update` resolves an unmerged PR; inspect current status/source. Do not mask the error by disabling skills/memory or adding a duplicate-ID hook that might block the good call first. Apply backports only with authorization and focused regression tests.

Setting-only workaround checks: distinguish `display.streaming` (rendering) from `model.streaming` (API preference). Do not assume the latter bypasses Responses SSE: in the inspected implementation, `_dispatch_nonstreaming_api_request` still routes `codex_responses` to `_run_codex_stream`, and `run_codex_stream` overwrites `stream=True`. An offline dispatch probe with `_disable_streaming=True` and `stream=False` confirmed that route. Recheck installed code before advising the toggle. Serializing calls also does not repair a single logical call duplicated during stream assembly. A supported model/provider using another API transport can avoid this parser, but routing and compatibility must be verified; do not blindly force a Responses-only model onto Chat Completions.

A narrow behavioral mitigation may prevent secondary retries: only when the same call ID demonstrably has a successful populated invocation and an empty duplicate, do not repeat the completed operation or diagnose a missing dependency solely from the empty copy; verify state for mutations or ambiguity. Never suppress genuine failures, valid zero-argument calls, or guardrails. This does not prevent the duplicate, remove UI warnings, or repair transcript state. Put any user-approved active mitigation in local behavior policy; do not present it as a parser fix.

