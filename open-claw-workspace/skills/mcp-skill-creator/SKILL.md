---
name: mcp-skill-creator
user-invocable: false
description: >
  Create minimal MCP-based skills from an existing mcporter server. Use when the user asks to
  create a new skill wrapping an MCP server, or wants a slash command for an MCP integration.
  Generates a lightweight SKILL.md that avoids duplicating MCP schema information.
---

# MCP Skill Creator

Generates minimal skill wrappers for MCP servers already configured in `config/mcporter.json`.

## Process

1. **Identify the MCP server.** User provides the server name (must exist in mcporter config).
2. **Inspect the server.** Run `mcporter list <server>` to discover available tools and understand the server's purpose.
3. **Gather conventions.** Ask the user (or infer from context):
   - What slash command should trigger it? (default: `/<server_name>`)
   - Any default project/context/target? (e.g., default recipe collection, default project)
   - Any behavioral rules? (e.g., "always confirm before deleting", "prefer bulk operations")
   - Any workflow sequences? (e.g., "always resolve IDs before creating")
4. **Generate the SKILL.md** using the template below.
5. **Write to** `skills/<name>/SKILL.md`.

## Template

```markdown
---
name: <server_name>
user-invocable: false
description: >
  <One-line description of what this skill does and when to use it.
  Mention the slash command trigger and key capabilities.>
---

# <Display Name>

Interacts with <service> through the `<server_name>` MCP server.

Tool names, parameters, and schemas are provided by the MCP server at runtime. Run `mcporter list <server_name>` to inspect available tools if needed.

## Execution

\`\`\`bash
mcporter call <server_name>.<tool> param=value
mcporter call <server_name>.<tool> --args '{"param": "value"}'
\`\`\`

## Conventions

- <Behavioral rules, defaults, and workflow notes specific to this integration.>
- <Keep this short -- only what the model can't infer from the MCP schema.>
```

## Conventions

- Confirm the skill name and MCP server with the user before generating files
- Always run `mcporter list <server>` to verify the server exists before generating
- Generated skills should follow openclaw section ordering conventions
- Never include MCP schema details in generated SKILL.md — they come from the server at runtime

## Principles

- **Never duplicate MCP schemas.** Tool names, parameters, and descriptions come from the server at runtime.
- **Only document what the model can't infer:** default targets, workflow sequences, behavioral rules, ID resolution patterns.
- **Keep it under 50 lines.** If the skill needs more, it's probably doing too much.
- **One slash command = one skill.** Don't bundle unrelated MCP servers.
