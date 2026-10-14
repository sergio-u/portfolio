---
name: mealie
description: >
  Manage recipes, meal plans, and shopping lists on the self-hosted Mealie instance.
  Use when the user asks to search, create, import, or update recipes, plan meals,
  manage shopping lists, or organize with categories/tags/tools.
  Triggers on "mealie", "recipe", "meal plan", "shopping list", "what's for dinner",
  "import recipe", "add to meal plan", "add recipe".
---

# Mealie

Manage recipes, meal plans, and shopping lists via the Mealie REST API.

## Execution

This skill now uses the Mealie REST API directly. The legacy MCP skill is archived on `<user>@<home-server>`, but REST is the canonical path because it supports full metadata, organizers, notes, and images.

Load env vars from `~/.openclaw/.env` if the shell has not already loaded them:

```bash
set -a
. ~/.openclaw/.env
set +a
AUTH="Authorization: Bearer $MEALIE_API_KEY"
```

Then call endpoints:

```bash
curl -s -H "$AUTH" "$MEALIE_BASE_URL/api/recipes?search=chicken"
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name": "New Recipe"}' "$MEALIE_BASE_URL/api/recipes"
```

## Recipes

### Search / List

```bash
curl -s -H "$AUTH" "$MEALIE_BASE_URL/api/recipes?search=chicken&page=1&perPage=20"
```

Query params: `search` (free text), `categories`, `tags`, `tools`, `foods` (arrays of IDs), `requireAllCategories`, `requireAllTags` (bool), `orderBy`, `orderDirection` (asc/desc), `page`, `perPage`.

Returns paginated `items[]` of recipe summaries (id, name, slug, description, image, rating, dateAdded).

### Get recipe details

```bash
curl -s -H "$AUTH" "$MEALIE_BASE_URL/api/recipes/$SLUG"
```

Returns full recipe: ingredients, instructions, categories, tags, tools, notes, nutrition, times, settings.

### Create (minimal)

```bash
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name": "Recipe Name"}' "$MEALIE_BASE_URL/api/recipes"
```

Returns the new recipe's slug. Follow up with PATCH to add ingredients, instructions, and metadata.

### Import from URL

```bash
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/recipe", "includeTags": false}' \
  "$MEALIE_BASE_URL/api/recipes/create/url"
```

Returns the new slug. Mealie scrapes the page and populates the recipe automatically.

Bulk import:

```bash
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"imports": [{"url": "https://..."}, {"url": "https://..."}]}' \
  "$MEALIE_BASE_URL/api/recipes/create/url/bulk"
```

### Update

```bash
curl -s -X PATCH -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"description": "...", "recipeIngredient": [...], "recipeInstructions": [...]}' \
  "$MEALIE_BASE_URL/api/recipes/$SLUG"
```

All fields optional. Key fields: `name`, `description`, `recipeServings`, `recipeYield`, `totalTime`, `prepTime`, `cookTime`, `recipeCategory`, `tags`, `tools`, `recipeIngredient`, `recipeInstructions`, `notes`, `nutrition`, `orgURL`, `rating`.

Categories, tags, and tools require objects with IDs -- look them up first via the organizer endpoints below.

#### Ingredient format (IMPORTANT)

**Do NOT pass `food` or `unit` objects** — they cause `ValueError` unless they reference existing DB entries with valid IDs. Instead, set `quantity: 0` and put the full human-readable ingredient string in both `note` and `display`. Mealie prepends the rendered `quantity` to `display`, so a non-zero quantity will duplicate any number already in the text.

Correct format:
```json
{
  "referenceId": "<uuid>",
  "quantity": 0.0,
  "unit": null,
  "food": null,
  "note": "2 tbsp extra virgin olive oil",
  "display": "2 tbsp extra virgin olive oil",
  "title": null,
  "originalText": null
}
```

**Wrong** (causes doubled display like "2 2 tbsp olive oil" or ValueError):
```json
{"quantity": 2, "unit": {"name": "tbsp"}, "food": {"name": "olive oil"}, "note": "...", "display": "2 tbsp olive oil"}
```

#### Instruction format

Each instruction's `id` field **must be a valid UUID** (not a friendly name like "step-1").

```json
{
  "id": "<uuid>",
  "title": "Build the base",
  "text": "Heat olive oil...",
  "summary": "",
  "ingredientReferences": []
}
```

### Delete

```bash
curl -s -X DELETE -H "$AUTH" "$MEALIE_BASE_URL/api/recipes/$SLUG"
```

### Upload image

Every manually created or merged recipe should get an image when a source image is available.

Preferred approach: extract `og:image` from the best source page, then use Mealie's direct-image endpoint. The URL must be a real image file (`.jpg`, `.jpeg`, `.png`, `.webp`); page URLs fail with `Url is not an image`.

```bash
python3 - <<'PY'
import re, requests, sys
html = requests.get(sys.argv[1], timeout=20, headers={"User-Agent": "Mozilla/5.0"}).text
for pattern in [
    r'<meta[^>]*property=["\\\']og:image["\\\'][^>]*content=["\\\']([^"\\\']+)',
    r'<meta[^>]*content=["\\\']([^"\\\']+)["\\\'][^>]*property=["\\\']og:image["\\\']',
    r'https://[^"\\\']+\\.(?:jpg|jpeg|png|webp)[^"\\\']*',
]:
    matches = re.findall(pattern, html, flags=re.I)
    if matches:
        print(matches[0].replace('\\u0026', '&'))
        break
PY "https://example.com/recipe-page"
```

Set image from direct URL:

```bash
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/photo.jpg"}' \
  "$MEALIE_BASE_URL/api/recipes/$SLUG/image"
```

If direct URL import fails, download and upload as multipart:

```bash
curl -sL "<direct-image-url>" -o /tmp/recipe-img.jpg
curl -s -X PUT -H "$AUTH" \
  -F "image=@/tmp/recipe-img.jpg;type=image/jpeg" \
  -F "extension=.jpg" \
  "$MEALIE_BASE_URL/api/recipes/$SLUG/image"
```

## Meal Plans

### List

```bash
curl -s -H "$AUTH" "$MEALIE_BASE_URL/api/households/mealplans?start_date=2026-04-05&end_date=2026-04-12"
```

### Today's meals

```bash
curl -s -H "$AUTH" "$MEALIE_BASE_URL/api/households/mealplans/today"
```

### Create

```bash
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"date": "2026-04-05", "entryType": "dinner", "recipeId": "<uuid>"}' \
  "$MEALIE_BASE_URL/api/households/mealplans"
```

Entry types: `breakfast`, `lunch`, `dinner`, `side`, `snack`, `drink`, `dessert`.

Either link a recipe via `recipeId`, or use `title`/`text` for a free-form entry.

### Random meal

```bash
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"date": "2026-04-05", "entryType": "dinner"}' \
  "$MEALIE_BASE_URL/api/households/mealplans/random"
```

## Shopping Lists

### List all

```bash
curl -s -H "$AUTH" "$MEALIE_BASE_URL/api/households/shopping/lists"
```

### Create list

```bash
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name": "Weekly Groceries"}' "$MEALIE_BASE_URL/api/households/shopping/lists"
```

### Get list with items

```bash
curl -s -H "$AUTH" "$MEALIE_BASE_URL/api/households/shopping/lists/$LIST_ID"
```

### Add recipe ingredients to list

```bash
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"recipeIncrementQuantity": 1}' \
  "$MEALIE_BASE_URL/api/households/shopping/lists/$LIST_ID/recipe/$RECIPE_ID"
```

### Add items manually (bulk)

```bash
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d '[{"shoppingListId": "<uuid>", "note": "Olive oil", "quantity": 1}]' \
  "$MEALIE_BASE_URL/api/households/shopping/items/create-bulk"
```

## Organizers (Categories, Tags, Tools)

All three follow the same pattern. Replace `categories` with `tags` or `tools`.

### List

```bash
curl -s -H "$AUTH" "$MEALIE_BASE_URL/api/organizers/categories"
```

### Create

```bash
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name": "Italian"}' "$MEALIE_BASE_URL/api/organizers/categories"
```

### Lookup by slug

```bash
curl -s -H "$AUTH" "$MEALIE_BASE_URL/api/organizers/categories/slug/italian"
```

## Ingredient Parser

Parse natural-language ingredient strings into structured data (quantity, unit, food).

```bash
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"ingredients": ["2 cups flour", "1 tbsp olive oil"], "parser": "nlp"}' \
  "$MEALIE_BASE_URL/api/parser/ingredients"
```

Parsers: `nlp` (default), `brute`, `openai`.

## Typical Workflows

### Full recipe creation

1. Create recipe: `POST /api/recipes` with `{"name": "..."}` -- get slug.
2. Build flat ingredients: `quantity: 0`, `unit: null`, `food: null`, full text in `note` and `display`.
3. Build instructions with UUID `id` values.
4. Look up or create organizer objects for categories, tags, and tools.
5. Update recipe: `PATCH /api/recipes/{slug}` with ingredients, instructions, description, servings/yield, times, organizers, notes, and `orgURL`.
6. Upload image from the best source page's direct image URL.
7. Re-fetch `GET /api/recipes/{slug}` and inspect the rendered ingredient/instruction display before telling the user it is done.

For adapted/combined recipes, notes must include source attribution and adaptation context:
- all original source URLs
- what was changed and why
- useful source tips retained
- heat/substitution scaling
- meal-prep/storage/reheating notes
- brief technique notes that help Sergio learn

### Import and enrich from URL

1. Import: `POST /api/recipes/create/url` with `{"url": "..."}` -- get slug
2. Review: `GET /api/recipes/{slug}` -- check what was scraped
3. Enrich: `PATCH /api/recipes/{slug}` -- fix/add missing metadata, categories, tags

### Meal planning for the week

1. Search recipes: `GET /api/recipes?search=...` or browse by category
2. Create plan entries: `POST /api/households/mealplans` for each day/meal
3. Generate shopping list: create a list, then add recipe ingredients for each planned recipe

### Grocery list to Todoist

When the user asks to push a grocery/shopping list to Todoist (e.g., after meal planning):

1. **Collect items** from the Mealie shopping list (`GET /api/households/shopping/lists/$LIST_ID`) or from the recipe ingredients of planned meals.
2. **Categorize each item** by grocery aisle/section: `Produce`, `Dairy`, `Meat`, `Pantry`, `Frozen`, `Bakery`, `Beverages`, `Snacks`, `Spices`, `Other`. Infer from the ingredient name.
3. **Create flat tasks directly in Personal > Groceries** (`projectId: "<id>"`, `sectionId: "<id>"`).
   - NO parent task, NO subtasks — just flat items in the section.
   - Each item prefixed with an aisle tag AND the dish name:
   ```
   [Produce] Green cabbage, 3/4 lb — Gyoza
   [Meat] Ground pork, 1/2 lb — Gyoza
   [Dairy] Greek yogurt x2 — Overnight Oats
   [Pantry] Olive oil — Shrimp
   ```
   - Sort items in rough shopping order: Meat → Produce → Dairy/Refrigerated → Frozen → Pantry → Spices.
4. **Combine duplicates** across recipes — if two recipes need onions, merge into one task with the combined quantity and list both dishes.
5. **Skip pantry staples** the user likely has (salt, pepper, cooking oil, sugar) unless they ask for a complete list.

Use `mcporter call todoist.add-tasks` with batches of up to 25 items. All tasks get labels `["AI"]`. Remember: use **camelCase** keys (`projectId`, `sectionId`) — snake_case is silently ignored.

## Reference

| Entity | Name | Slug/ID |
|---|---|---|
| | | |

> **Maintenance:** Populate this table with frequently used recipe IDs, meal plan slugs, and category/tag IDs as you discover them.

## Conventions

- REST API is canonical; do not route new work through the legacy MCP flow unless Sergio explicitly asks.
- Always look up a recipe by search or slug before updating -- never guess slugs or IDs.
- When creating recipes manually, use the flat ingredient format (quantity=0, full string in note/display) and step-by-step instructions with UUID ids.
- For merged/adapted recipes, always preserve source attribution in `notes` and set `orgURL` to the primary/best source.
- Add an image for every saved recipe when a source image is available.
- When adding to a meal plan, get the recipe ID first (from search results or recipe detail).
- Dates use ISO format: `YYYY-MM-DD`.
- Categories, tags, and tools require IDs -- look them up or create them via organizer endpoints before assigning to recipes.
- Parse JSON output and present it readably -- do not dump raw JSON to the user.
- Confirm with the user before destructive operations (delete recipe, clear shopping list).

## Authentication

Env vars loaded from `~/.openclaw/.env`:

- **`MEALIE_BASE_URL`** -- Mealie instance URL (no trailing slash)
- **`MEALIE_API_KEY`** -- long-lived API token (created via the Mealie UI or `POST /api/users/api-tokens`)
- **Header:** `Authorization: Bearer $MEALIE_API_KEY`

Do not hardcode the Mealie URL or token in the skill. The legacy skill had a fixed API base and token location; this local skill intentionally uses env vars instead.

## Requirements

- `curl` for all API calls
- Env vars `MEALIE_BASE_URL` and `MEALIE_API_KEY` set in `~/.openclaw/.env`

## Troubleshooting

### API connection failures

Verify `MEALIE_BASE_URL` is reachable: `curl -s "$MEALIE_BASE_URL/api/app/about"`. If the instance is behind a reverse proxy or on a local network, check that the host is accessible from the current machine.

### Authentication errors

A `401 Unauthorized` response means the API key is invalid or expired. Generate a new token from the Mealie UI (User Settings > API Tokens) or via `POST /api/users/api-tokens` and update `~/.openclaw/.env`.

### Recipe import returns empty content

Some sites block scrapers. Try fetching the URL in a browser first to confirm the recipe content is publicly accessible. If Mealie can't scrape it, create the recipe manually and paste the content.
