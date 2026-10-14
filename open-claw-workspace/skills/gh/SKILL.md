---
name: gh
description: >
  Search GitHub for repos, issues, PRs, discussions, code, and more via the gh CLI.
  Use when the user says "search GitHub", "find issues", "list PRs", "search repos",
  "GitHub code search", or asks to look something up on GitHub.
---

# GitHub CLI

## Execution

```bash
gh search repos <query> [flags]
gh search issues <query> [flags]
gh search prs <query> [flags]
gh search code <query> [flags]
gh search commits <query> [flags]
```

Use `--json <fields>` for machine-readable output when parsing results. Use `--limit` to control result count (default 30).

## Reference

- Use qualifiers to narrow searches: `--language`, `--owner`, `--repo`, `--label`, `--state`, `--sort`, `--order`.
- For discussions, use `gh api` since there's no top-level search command: `gh api search/topics?q=...` or GraphQL via `gh api graphql`.

## Conventions

- When the user asks to "look something up on GitHub" or "find a repo/issue", use this skill.
- Present results concisely -- title, URL, and key metadata. Don't dump raw JSON at the user.
- Use `--json` for machine-readable output when you need to parse or filter results programmatically.
- Confirm before performing any destructive operations (deleting repos, closing issues, etc.).
- Summarize results cleanly -- highlight the most relevant matches first.

## Authentication

Before running any `gh` command, ensure authentication:

1. **Check status:** `gh auth status`
2. **If not authenticated**, try the PAT from the secrets env file:
   ```bash
   grep "^GH_TOKEN=" ~/.openclaw/.env | cut -d= -f2- | gh auth login --with-token
   ```
3. **If no PAT available**, fall back to `gh auth login` (interactive, requires user).

Once authenticated, `gh` persists the token in `~/.config/gh/hosts.yml` for future sessions.

## Requirements

- `gh` CLI must be installed.
- A GitHub PAT stored in `~/.openclaw/.env` as `GH_TOKEN`, or an existing `gh auth login` session.

## Troubleshooting

- **Auth failures**: Run `gh auth status`. If not logged in, try re-authenticating from the PAT (step 2 above). If the PAT is expired or missing, ask the user to re-authenticate interactively or generate a new PAT.
- **Rate limits**: GitHub API rate limits apply (5,000 requests/hour for authenticated users). If you hit a limit, wait or reduce `--limit` values.
- **Empty results**: Double-check qualifiers and query syntax. Some search types require specific qualifier formats.
