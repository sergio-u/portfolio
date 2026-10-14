# Recipe Synthesis Rules

Detailed rules for meal-planner recipe synthesis, meal prep, Mealie metadata, grocery lists, and beginner-friendly precision. Read when synthesizing or saving recipes.

## Rules

### Spice Rules
- **Use whole when:** star anise, Sichuan peppercorn, cumin seed, coriander seed, fennel seed, cloves, cinnamon sticks, cardamom pods, black peppercorns, dried chiles -- all available at Asian/Latin groceries in Seattle
- **Pre-ground is fine for:** turmeric, smoked paprika, MSG, onion/garlic powder (grinding these yourself adds nothing)
- **Build blends fresh:** instead of "five spice powder," list the 3-4 relevant whole spices to grind. Explain the blend once, reference it after.

### Vegetable Rules
- **Prefer:** spinach, carrots, bell peppers, onion, cabbage (napa or green), broccoli, mushrooms (any), zucchini, frozen peas/corn, sweet potato, green beans, kale
- **Avoid unless requested:** bok choy (expensive in Seattle), high-waste items (half a celery bunch), anything ultra-seasonal or specialty
- **Frozen is fine:** spinach, peas, corn, edamame, broccoli -- cheaper, no waste, always available

### Meal Prep Rules
- The main component (protein + sauce + most veg) should keep 3-4 days refrigerated
- Starches that degrade (pasta, fresh noodles): note "cook fresh daily, 5 min"
- Starches that hold (rice, roasted potato): include in prep
- Garnishes/toppings: list separately as "day-of" additions
- If a recipe benefits dramatically from a fresh element (crispy tofu, fried egg on top), note it as an optional quick day-of step

### Effort Calibration
The user may specify an effort level for the week:
- **Low effort:** One-pot/pan meals, sheet pan dinners, minimal knife work, dump-and-simmer. Max 30 min active time.
- **Medium effort (default):** Some knife work, 1-2 pans, a marinade or sauce from scratch. 30-45 min active.
- **High effort:** Wok technique, fresh pasta, multi-component dishes, deep frying. 45-90 min active. Reserved for weekends or when the user is feeling ambitious.

### Precision Rules
The user is learning to cook and doesn't have strong intuition yet. Every recipe must be specific enough to follow without guessing.

**Quantities -- always explicit:**
- Never "salt to taste" alone. Write: "1/2 tsp kosher salt (adjust to taste)"
- Never "a drizzle of oil." Write: "1 tbsp oil"
- Spices: always in tsp/tbsp. "A pinch" = "1/8 tsp"
- Liquids: cups, tbsp, or ml. No "a splash"

**Times -- always give a number:**
- Never "cook until golden" alone. Write: "cook 3-4 min, until golden brown on the bottom"
- Never "sauté until fragrant." Write: "stir 20-30 seconds, until fragrant"
- Never "simmer until thickened." Write: "simmer 8-10 min, stirring occasionally, until sauce coats the back of a spoon"
- Oven times: always give a range and a visual cue. "Bake 20-25 min, until edges are crisp and center is set"

**Temperatures:**
- Stove: translate "medium-high" into what to look for. "Medium-high heat (oil should shimmer and a drop of water sizzles immediately)"
- Oven: always in F with C in parentheses. "400F (200C)"

**Knife work:**
- Specify thickness/size. Not "dice the carrots" but "dice carrots into 1/2 inch pieces" or "slice 3mm thin on the diagonal"
- When a cut matters for cooking time, say why. "Slice thin (3mm) so they cook through in the stir fry time"

**The pattern:** specific number + descriptive cue. The number lets a beginner follow exactly; the cue teaches them what to look for over time.

### Flavor Preferences
- **Spicy food is welcome.** If a dish benefits from heat, lean into it -- use the higher end of chili ranges, add a "kick it up" note with extra amounts.
- Default heat level: medium-spicy. Provide an easy way to scale up (e.g., "1-2 tbsp sambal for medium, 3 tbsp for hot").

### Mealie Recipe Image
Every recipe saved to Mealie must have an image. After creating the recipe:

1. Pick the best source URL (the one with the most appetizing hero photo).
2. Extract the `og:image` URL from that page's HTML using trafilatura's `fetch_url` + regex:
   ```python
   from trafilatura import fetch_url
   import re
   html = fetch_url(url)
   og = re.findall(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\'>]+)', html)
   ```
3. POST the direct image URL to Mealie's scrape-image endpoint:
   ```bash
   curl -s -X POST "$MEALIE_URL/api/recipes/$SLUG/image" \
     -H "Authorization: Bearer $MEALIE_KEY" \
     -H "Content-Type: application/json" \
     -d '{"url": "<direct-image-url>"}'
   ```
   The URL must point to an actual image file (jpg/png/webp), not a page URL.
4. If the og:image extraction fails or returns a page URL, fall back to searching the HTML for large recipe-related image URLs.

### Mealie Notes & Sources
When saving to Mealie, use the recipe notes field to include:
- **Source URLs** -- all original recipes used for synthesis
- **Useful tips** from the original recipes (e.g., "freezing tofu first makes it chewier")
- **Substitution notes** (what was changed from originals and why)
- **Spice/heat scaling** suggestions
- **Meal prep specific notes** (storage life, reheating tips, what to cook fresh)
- **Why certain techniques matter** (brief -- helps the user learn)

Notes are added via the Mealie API directly since the MCP update tool only covers ingredients/instructions:
```bash
curl -s -X PATCH "$MEALIE_URL/api/recipes/$SLUG" \
  -H "Authorization: Bearer $MEALIE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"notes": [{"title": "...", "text": "..."}], "orgURL": "..."}'
```


## Optional Save / Grocery Details

### 6. Optional: Save to Mealie

If the user confirms, save each recipe using the mealie skill:
```bash
npx mcporter call mealie.create_recipe --args '{"name": "...", "ingredients": [...], "instructions": [...]}'
```

After creating the recipe, PATCH full metadata via the Mealie API. Every saved recipe **must** have all of the following:

**Required metadata (PATCH to `/api/recipes/{slug}`):**
- `description` -- 1-2 sentence summary of the dish and adaptations made
- `recipeServings` -- number (e.g. 4)
- `recipeYield` -- human-readable yield string (e.g. "12 enfrijoladas", "6 cups soup")
- `recipeYieldQuantity` -- numeric yield count
- `prepTime` -- ISO 8601 duration (e.g. "PT20M")
- `performTime` -- active cook time, ISO 8601 (e.g. "PT25M")
- `cookTime` -- total cook time, ISO 8601
- `totalTime` -- prep + cook, ISO 8601
- `orgURL` -- primary source recipe URL
- `recipeCategory` -- array of category objects (e.g. Mexican, Dinner, Vegetarian)
- `tags` -- array of tag objects (e.g. meal-prep, beans, quick)
- `tools` -- array of tool objects (e.g. Blender, Skillet, Wok)
- `notes` -- see "Mealie Notes & Sources" section below

**Creating organizers (categories, tags, tools):**
Categories, tags, and tools must exist in Mealie before they can be assigned to a recipe. For each:
1. Check if it already exists: `GET /api/organizers/categories`, `/tags`, or `/tools`
2. If not, create it: `POST /api/organizers/{type}` with `{"name": "..."}`
3. Use the returned `id`, `name`, and `slug` in the recipe PATCH

Reuse existing categories/tags/tools when possible rather than creating duplicates.

### 7. Optional: Generate Grocery List

If the user confirms, consolidate all ingredients into a grocery list and add to Todoist using the todoist skill:
- Deduplicate and combine quantities across recipes
- Group by store section (produce, protein & refrigerated, pantry, spices, dairy & fridge, dry goods, etc.)
- Add to the Groceries section of the AI project (`sectionId: <id>`)

**Structure: parent task + subtasks (required)**
Each store section gets one parent task as the category header, with individual items as subtasks beneath it. Do NOT put items in the description field.

Parent task format: `Groceries: <Section Name>` (e.g. `Groceries: Produce`)

Each subtask content: `<item name>, <quantity> (<dish it's used in>)`
- For shared ingredients: `(teriyaki + tacos)` or `(all recipes)`
- For optional items: `(optional — natto)`
- For pantry check items: `(check pantry first — tacos)`

Example structure:
```
Groceries: Produce                          ← parent task
  └ Broccoli, 1 large head (teriyaki)       ← subtask
  └ Green onions, 2 bunches (all recipes)   ← subtask
  └ Fresh ginger, small knob (teriyaki)     ← subtask

Groceries: Protein & Refrigerated           ← parent task
  └ Extra-firm tofu, 2 blocks (teriyaki)    ← subtask
```

Add all subtasks with `parentId` set to the parent task's ID. After creating subtasks, leave descriptions empty on parent tasks.
