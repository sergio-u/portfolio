# Habit System Workflow

Temporary workflow for Sergio's habit system.

Use this when the user asks to:
- review the habit system week by week
- update the current week plan
- create the next week guide
- do a weekly review
- adjust the plan in-flight during the week
- compare what was planned vs what actually happened

This workflow is designed to work with these notes:
- `~/Documents/Sync/Notebook/2026-H1/20_Active_Projects/Minimal Habit System.md`
- `~/Documents/Sync/Notebook/2026-H1/20_Active_Projects/Week 1 - Operating Guide.md`
- future week guides in the same folder, e.g. `Week 2 - Operating Guide.md`
- relevant daily notes in `~/Documents/Sync/Notebook/2026-H1/10_Daily/`

---

## Goals

This workflow should help:
- keep the habit system alive week by week
- update the plan without restarting from scratch
- turn daily friction into small structural improvements
- distinguish between temporary issues and systemic issues
- keep the notes aligned with the real workflow in Todoist / Calendar / Apple reminders

---

## Core Rules

- Prefer revising the current system over creating a new one.
- Change one major thing at a time unless something is clearly broken.
- Update the current week guide for tactical changes.
- Update the master plan only for enduring lessons, structural changes, or clarified principles.
- If the user notices a problem during the week, capture it immediately instead of trusting memory.
- Keep changes concrete and reversible.
- Avoid turning the notes into a giant life-ops bureaucracy.

---

## Note Roles

### Master plan
`Minimal Habit System.md`

Use for:
- philosophy
- system architecture
- tool roles
- phased rollout
- recurring operating rules
- durable lessons
- revision log entries

### Weekly guide
`Week N - Operating Guide.md`

Use for:
- current week's focus
- current defaults and anchors
- exact Week N behavior rules
- what counts as success this week
- current reminder / calendar / Todoist setup
- tactical experiments for this week

### Daily notes
`10_Daily/YYYY-MM-DD.md`

Use for:
- what helped
- what got in the way
- notable misses, wins, or friction
- any observation that should be reviewed at the end of the week

---

## Weekly Review Workflow

Use this when the user asks for a weekly review or when creating the next week's plan.

### Step 1: Read the key notes
Read:
1. `Minimal Habit System.md`
2. the current week's operating guide
3. relevant daily notes for the past 7 days (or since the last review)

If a week guide for the next week does not exist yet, prepare to create it.

### Step 2: Extract the real signals
Look for:
- which habits actually happened
- which habits kept slipping
- whether the problem was timing, friction, energy, clarity, or too many commitments
- whether Apple / Calendar / Todoist setup helped or got ignored
- whether the floor was too high or too vague

### Step 3: Write a short review summary
Keep it practical. Cover:
- wins
- friction points
- what seems to be working
- what needs to change
- whether to keep, lower, remove, or add anything

This can be written into:
- the current week's operating guide under a review section, or
- a dedicated weekly review section appended near the end

### Step 4: Decide the next week's single biggest adjustment
Examples:
- keep the same 4 habits another week
- add one new weekday habit
- change the movement anchor
- lower a floor
- simplify a task name
- add a calendar block only if the current cue is failing

Prefer one clear adjustment over many small speculative ones.

### Step 5: Update notes
Update the weekly guide with:
- the actual anchor that worked
- the current defaults
- any tactical changes for the next week
- the new success criteria if needed

Update the master plan only if the change is durable enough to matter beyond one week.

### Step 6: Add a revision log entry if warranted
If the change reflects a meaningful system lesson, append a short entry to the master plan revision log.

Good revision log items:
- movement works better as a post-work transition than a fixed calendar block
- shutdown improved after simplifying the definition of success
- Todoist subtasks were less visible than flat tasks

Not every weekly tweak needs a revision log entry.

---

## In-Flight Adjustment Workflow

Use this when the user says something like:
- this part is not working
- I changed a reminder
- this task name is unclear
- I want to tweak this now
- this should happen at a different time

### Step 1: Identify the scope
Ask internally:
- Is this tactical for only the current week?
- Or is it a durable system lesson?

### Step 2: Update the right note
- Tactical / temporary -> update the current week's guide
- Durable / structural -> update the master plan too

### Step 3: Preserve reality
Reflect the actual setup.
Examples:
- if the user added a 5:30 PM Apple reminder, write that down
- if movement is now defined as walk by default + swim once + yoga fallback, write that down
- if Calendar already has sleep/work blocks, do not keep suggesting redundant recurring blocks

### Step 4: Keep changes narrow
Do not rewrite the whole system because one detail changed.
Make the smallest update that keeps the notes honest and useful.

---

## Creating the Next Week Guide

When moving from one week to the next:

### Naming
Create a new note in:
`~/Documents/Sync/Notebook/2026-H1/20_Active_Projects/`

Pattern:
- `Week 2 - Operating Guide.md`
- `Week 3 - Operating Guide.md`
- etc.

### Structure
Start from the previous week's guide, then revise:
- current focus
- current active habits
- actual cueing / reminder setup
- what changed from last week
- success criteria for this week
- bad-day fallback

Avoid blindly copying stale assumptions.

### Linking
Where useful:
- link the new week guide from the master plan
- reference the previous week guide if comparison matters

---

## Suggested Sections for Weekly Guides

A weekly guide should usually include:
- Week goal
- current active habits
- what each habit means this week
- tool roles for this week
- ideal day
- bad-day fallback
- success criteria
- things to avoid
- end-of-week review questions
- optional section: changes made this week

---

## Suggested Sections for Review Notes Inside Weekly Guides

If adding a review section, use something like:

```markdown
## End of Week Review

### Wins
- ...

### Friction
- ...

### What worked
- ...

### What did not work
- ...

### Change for next week
- ...
```

For mid-week changes, use something like:

```markdown
## In-Flight Changes

### 2026-04-19
- Added 5:30 PM Apple reminder for movement
- Clarified movement defaults: walk by default, swim once this week, yoga as fallback
```

---

## Vault Update Pattern

When this workflow results in note changes:
1. edit or write the relevant note(s)
2. keep wiki-links valid
3. trigger Syncthing rescan for `2026-H1/20_Active_Projects` or the edited path

---

## Decision Heuristics

### Update only the week guide when:
- a reminder time changes
- a task gets renamed
- this week's default activity changes
- a temporary experiment is being tried
- the current week needs clearer instructions

### Update the master plan too when:
- a tool role changes
- a core principle changes
- a recurring pattern is discovered
- the phased rollout changes
- a lesson is likely to matter in future weeks

### Keep the same plan another week when:
- the system is still new
- inconsistency is caused by novelty wearing off, not by bad design
- the current habits have not had enough repetitions yet

### Add a new habit only when:
- the core floor is reasonably stable
- the user explicitly wants to expand
- the added habit has a very clear floor and anchor

---

## Preferred Style

- concise
- concrete
- reality-based
- no motivational fluff
- no giant rewrites unless asked
- make the notes easier to use, not more impressive to read
