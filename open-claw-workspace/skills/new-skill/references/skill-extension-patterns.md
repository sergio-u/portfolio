# Skill Extension Patterns

Use this reference when the user wants to evolve an existing skill, not just create a brand-new one.

This workspace already has good examples of 3 useful patterns:
- **Parent skill + sub-skills** (`gws`)
- **Main skill + attached workflow/recipe doc** (`obsidian` with `Habit System Workflow.md`)
- **Shared/helper skill + focused operational sub-skills** (`gws-shared` + `gws-calendar-*` family)

The goal is to choose the smallest structure that fits the recurring workflow.

---

## Pattern 1: Extend an Existing Skill In-Place

Use this when:
- the workflow clearly belongs to an existing skill
- the user already thinks of it as part of that skill
- no new slash command is needed
- the new logic is mostly instructions / operating procedure, not a whole new domain

Example:
- `obsidian` gained a temporary workflow doc for habit-system weekly reviews

Recommended structure:

```text
skills/<skill>/
  SKILL.md
  <Workflow Name>.md
```

How to implement:
1. Create a focused workflow/recipe/reference doc in the skill folder
2. Add a short pointer in `SKILL.md`
3. Keep `SKILL.md` lean; move step-by-step operating loops into the separate doc
4. Only update the skill frontmatter if the new workflow materially changes when the skill should trigger

Good fits:
- weekly review loop
- triage workflow
- migration checklist
- repeatable operating recipe
- temporary or evolving process guidance

---

## Pattern 2: Parent Skill + Sub-Skills

Use this when:
- the domain is broad
- there are several distinct operation clusters
- different user requests should load different focused instructions
- the same auth / binary / API surface is shared across many subdomains

Example:
- `gws` parent skill plus `gws-calendar`, `gws-drive`, `gws-sheets`, etc.

Recommended structure:

```text
skills/<parent>/
  SKILL.md
  <parent>-shared/
    SKILL.md              # optional helper/shared instructions
  <parent>-<domain>/
    SKILL.md
  <parent>-<operation>/
    SKILL.md
```

How to implement:
1. Keep the parent `SKILL.md` as the overview, auth/binary entry point, and quick reference
2. Put domain-specific procedures in sub-skill folders
3. Link sub-skills from the parent via a table
4. If auth/global syntax is reused, centralize it in a shared/helper sub-skill

Good fits:
- large APIs
- one CLI used across several domains
- many operations that would make one SKILL.md too heavy

---

## Pattern 3: Shared Skill + Focused Operational Sub-Skills / Recipes

Use this when:
- multiple sub-skills need the same auth, global flags, or safety rules
- the parent skill is mostly routing/overview
- some pieces are operational recipes rather than tool wrappers

Example shape:

```text
skills/<parent>/
  SKILL.md
  <parent>-shared/
    SKILL.md
  <parent>-<operation>/
    SKILL.md
  references/
    ...
```

Use a shared/helper skill when:
- repeated instructions would otherwise be copied across many sub-skills
- there is a stable core that other sub-skills rely on

Use a workflow doc instead when:
- only one skill needs the extra process
- the new content is just a recipe, review loop, checklist, or operating rhythm

---

## Decision Heuristic

When the user asks for a new capability, decide in this order:

### 1. Does this belong inside an existing skill?
If yes, extend the existing skill instead of creating a new one.

### 2. Is it just a focused workflow/recipe/checklist?
If yes, add a workflow or recipe doc and point to it from the main `SKILL.md`.

### 3. Is the domain becoming too broad for one `SKILL.md`?
If yes, split into sub-skills.

### 4. Is there shared auth/syntax/safety guidance across many sub-skills?
If yes, add a shared/helper skill.

### 5. Only create a brand-new standalone skill when:
- the capability is genuinely separate
- it should have its own triggers / slash command
- extending an existing skill would make the structure worse, not better

---

## What to Update When Extending a Skill

When evolving an existing skill, review these files in order:

1. `SKILL.md`
   - Does it need a pointer to the new workflow/sub-skill?
   - Do trigger phrases need expanding?
   - Is the summary still accurate?

2. Supporting docs
   - Add a workflow, recipe, or reference file if the new logic is too detailed for `SKILL.md`

3. Reference/cache tables
   - Update if the skill depends on known IDs, names, or entities

4. Related skills table
   - Update parent skills when adding sub-skills

5. Conventions
   - Add any new confirmation, output, or operational rules introduced by the new capability

---

## Naming Guidance

### Workflow / recipe docs
Use descriptive names such as:
- `Habit System Workflow.md`
- `Inbox Triage Recipe.md`
- `Weekly Review Loop.md`
- `Migration Checklist.md`

### Sub-skills
Use parent-prefixed names:
- `gws-calendar`
- `gws-drive`
- `gws-shared`

Keep names:
- short
- obvious
- consistent with the parent

---

## Anti-Patterns

Avoid:
- creating a whole new skill for every small workflow
- stuffing long operating loops into `SKILL.md` when a separate doc would be cleaner
- duplicating auth / CLI syntax / shared rules across many sub-skills
- creating sub-skills when a single workflow doc would do
- changing triggers so broadly that a skill over-fires on unrelated requests

---

## Preferred Style

- extend before duplicating
- split only when structure improves
- keep the main skill as an overview and router
- keep workflows concrete and reusable
- prefer small, composable pieces over one giant skill file
