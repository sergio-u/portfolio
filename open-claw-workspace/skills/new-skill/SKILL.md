---
name: new-skill
description: >
  Create a new AgentSkill or evolve an existing one based on user input. Use ONLY when the user explicitly
  invokes this skill by name or asks to "create a new skill", "build a skill", "extend this skill",
  "update this skill", or add a workflow, recipe, or sub-skill to an existing skill.
  DO NOT auto-trigger for general skill-related questions.
---

# New Skill

Guide the user through designing and creating a new OpenClaw workspace skill, or extending an existing skill with workflows, recipes, helper docs, or sub-skills.

## Process

1. **Read the references** -- before generating any files:
   - `references/openclaw-conventions.md` -- OpenClaw-specific skill structure, execution patterns, auth patterns (this takes precedence over generic guidance)
   - `references/skill-design-guide.md` -- General AgentSkill design principles (progressive disclosure, frontmatter, testing)
   - `references/skill-examples.md` -- Condensed examples from our own workspace skills showing each execution pattern in practice
   - `references/skill-extension-patterns.md` -- How to extend existing skills with workflows, recipes, shared helpers, or sub-skills
   - `references/multi-agent-workflow.md` -- How to design skills with parallel subagent orchestration (read only when the task involves processing multiple independent units)

2. **Understand the user's intent** -- ask clarifying questions if needed:
   - Is this a brand-new capability, or should an existing skill be extended?
   - What should the skill or extension do? What tasks will it handle?
   - What should trigger it? (phrases, contexts, use cases)
   - What execution pattern fits? (CLI wrapper, uv run script, venv + repl, MCP wrapper, custom binary, pure shell, workflow/recipe doc, or multi-agent orchestration)
   - What resources does it need? (scripts, reference docs, assets)
   - Does an existing skill already handle part of this? (Check `~/.openclaw/workspace/skills/` -- delegate to existing skills instead of reimplementing. E.g., use scrapling for web fetching, trafilatura for article extraction, agent-browser for authenticated browsing.)

3. **Choose the smallest good structure**:
   - Extend an existing skill in place when the workflow clearly belongs there
   - Add a workflow/recipe doc when the new capability is mostly repeatable instructions rather than a new tool surface
   - Split into parent + sub-skills when one domain is getting too broad
   - Add a shared/helper skill when multiple sub-skills need the same auth, syntax, or safety rules
   - Create a brand-new standalone skill only when the capability is genuinely separate

4. **Design the skill or extension** using the conventions:
   - Write a clear, trigger-rich `description` in the frontmatter using `>` folded scalar
   - Follow the OpenClaw section order: Display Name > Execution > Domain > Reference > Conventions > Auth > Requirements > Troubleshooting
   - Keep SKILL.md lean -- move detailed API docs, operating loops, or reference material into `references/` or standalone workflow docs
   - Add a Reference/Cache table if the skill interacts with recurring entities/IDs
   - Only include scripts/assets/references that are genuinely reusable
   - Prefer delegation over duplication -- if another skill already handles fetching, parsing, or a sub-workflow, reference it instead of embedding equivalent logic. Domain skills (selectors, endpoints, workflows) + tool skills (scrapling, agent-browser) is the ideal split.
   - When extending an existing skill, update the parent SKILL.md so the new workflow/sub-skill is discoverable

5. **Create or update the skill files** in `~/.openclaw/workspace/skills/<skill-name>/`

6. **Validate** the result:
   - Frontmatter: name matches folder, description has WHAT + WHEN + trigger phrases, uses `>` multiline
   - Structure: follows section order, execution pattern is correct for the tool type
   - No README.md inside the skill folder
   - Reference tables present if applicable
   - Auth documented (no hardcoded secrets)
   - Conventions section present with confirmation rules and output formatting

## Reference

- `references/openclaw-conventions.md` -- OpenClaw skill structure, patterns, and conventions (read first)
- `references/skill-design-guide.md` -- General AgentSkill design guide (progressive disclosure, frontmatter, testing, distribution)
- `references/skill-examples.md` -- Condensed examples from our workspace skills
- `references/skill-extension-patterns.md` -- Patterns for evolving existing skills with workflows, recipes, shared helpers, and sub-skills
- `references/multi-agent-workflow.md` -- Designing skills with parallel subagent orchestration (file handoff, prompt templates, model selection, aggregation)

## Conventions

- Always read the references before generating or modifying skill files
- OpenClaw conventions take precedence over the generic design guide when they conflict
- Confirm the skill name, trigger phrases, and execution pattern with the user before creating files
- First decide whether to extend an existing skill or create a new one
- Prefer the smallest good structure: workflow doc < sub-skill < brand-new standalone skill
- Keep SKILL.md lean -- move detailed API docs, workflows, or references into `references/` files or standalone workflow/recipe docs
- Follow the OpenClaw section order: Display Name > Execution > Domain > Reference > Conventions > Auth > Requirements > Troubleshooting
- Use `>` folded scalar for multiline descriptions in frontmatter
- Folder name = slash command name (kebab-case, short, memorable)
- Include a Conventions section in every skill with confirmation rules and output formatting guidance
- Add `user-invocable: false` only if the skill should NOT be a slash command
- Prefer skill collaboration over duplication -- before adding scripts or tools to a new or existing skill, check if another skill (scrapling, trafilatura, agent-browser, etc.) already provides that capability. Skills should add domain knowledge and workflows, not reimplement shared tooling. Only bundle a dedicated script/tool when the existing skills genuinely can't cover the use case.
- When adding sub-skills or workflows to an existing skill, update the parent skill so the new pieces are discoverable.
