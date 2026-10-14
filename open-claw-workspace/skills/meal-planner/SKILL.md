---
name: meal-planner
user-invocable: false
description: >
  Synthesize one adapted recipe from multiple source recipe URLs, or plan a week
  of dinners from grouped URLs with ingredient overlap and waste reduction. Use
  when the user provides recipe links and asks to "merge recipes", "combine these
  recipes", "make a meal plan", "build a grocery list", or optionally save the
  result to Mealie/Todoist.
---

# Meal Planner

Synthesize recipes and weekly dinner plans from source URLs.

## Execution

1. Classify the request:
   - **Single dish:** 2+ URLs for one dish. Merge into one adapted recipe.
   - **Weekly plan:** URLs grouped by day/dish. Synthesize each dish, then optimize overlap.
2. Fetch every source recipe before synthesizing.
3. Report any extraction gaps or malformed recipe data.
4. Produce the merged recipe/plan with explicit quantities, times, and meal-prep notes.
5. Save to Mealie or create a Todoist grocery list only after the user confirms.

For detailed synthesis, precision, Mealie, and grocery-list rules, read `references/recipe-synthesis-rules.md`.

## Fetching Recipes

Preferred extraction command from the workspace root when the legacy web-extract skill exists:

```bash
VENV=/home/node/.openclaw/workspace/.venv
. $VENV/bin/activate && python3 /home/node/.openclaw/workspace/skills/web-extract/scripts/extract.py "<url>" --recipe
```

Fallbacks, in order:
- `web_fetch` with `maxChars=12000`
- source page JSON-LD recipe data, if available
- ask the user to paste the recipe only if automated extraction fails

After fetching, check each source for partial parsing issues:
- missing ingredients
- truncated instructions
- obvious unit/serving parse errors
- page fetched but no recipe card found

Do not silently skip failed URLs. Tell the user which sources failed and whether the remaining content was enough.

## Synthesis Defaults

Apply these unless the user overrides them:
- Minimum 4 portions.
- Meal-prep friendly: should still taste good on day 3.
- Nutritionally complete: protein + carb/base + vegetable + fat, unless the dish is intentionally an appetizer/side.
- No cilantro by default. Substitute flat-leaf parsley, Thai basil, mint, or green onion depending on cuisine.
- Spicy food is welcome; default to medium-spicy when it fits.
- Seattle grocery access: Latin, Asian, and American stores are available.
- Prefer affordable, versatile vegetables and avoid high-waste specialty items unless requested.

Apply user guidelines last: effort level, dietary constraints, preferred base, substitutions, spice level, or cuisine direction.

## Output Format

For a single dish, output:
- Recipe name
- Servings and prep/cook/total time
- Short source/merge note
- Ingredients grouped by component
- Numbered instructions with explicit quantities, timing, and visual cues
- Meal prep/storage notes
- Optional variations or heat scaling

For a weekly plan, also output:
- Dish list by day
- Shared ingredients and single-use/waste-risk ingredients
- Prep-day strategy
- Consolidated grocery list, if requested

## Weekly Optimization

For weekly plans:
- Reuse fresh herbs; pick at most 2-3 for the week.
- Standardize aromatics: garlic, ginger, onion, green onion.
- Reuse vegetables that require buying a full unit, or substitute them out.
- Prefer pantry sauces/condiments that carry across multiple recipes.
- If one protein repeats 3+ times, suggest variety.

## Optional Mealie Save

Only save after explicit user confirmation.

When saving adapted/merged recipes:
- Use the `mealie` skill/API conventions.
- Include all source URLs in notes.
- Include adaptation notes, useful source tips, heat scaling, meal-prep notes, and why important techniques matter.
- Add complete metadata: servings, yield, times, category/tags/tools, source URL, and notes.
- Add an image from the best source hero image when possible.

## Optional Todoist Grocery List

Only create after explicit user confirmation.

When creating a grocery list:
- Consolidate duplicate ingredients and quantities across dishes.
- Group by store section.
- Use parent tasks named `Groceries: <Section Name>` with individual items as subtasks.
- Include which dish uses each item.

## Conventions

- Confirm before external writes: Mealie saves, Todoist task creation, deletes, or bulk updates.
- Do not dump raw extracted recipe JSON unless debugging.
- Preserve attribution: keep source URLs visible in final notes or Mealie notes.
- Beginner-friendly precision: no vague "drizzle", "pinch", or "cook until done" without numbers and cues.
- If source recipes disagree, choose the technique that best improves flavor/texture and explain the choice briefly.

## Requirements

- Network access to fetch recipe URLs.
- Optional: legacy `web-extract` skill for structured extraction.
- Optional: `mealie` skill/API access for saving recipes.
- Optional: `todoist` skill/MCP access for grocery lists.

## Troubleshooting

- **Recipe page blocks extraction:** retry with `web_fetch`; if still blocked, ask for pasted recipe text.
- **Ingredients parsed but instructions missing:** use visible article text if available and flag the gap.
- **Mealie organizer IDs missing:** look up or create categories/tags/tools before PATCHing recipe metadata.
- **Image import fails:** retry with the source page `og:image`; if that is not a direct image URL, search HTML for a large jpg/png/webp recipe image.
