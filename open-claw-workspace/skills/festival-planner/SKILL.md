---
name: festival-planner
description: >
  Build personalized daily schedules for music festivals using Tidal library data,
  taste profile, friend plans, and venue maps. Use when the user says "plan my festival day",
  "coachella schedule", "festival plan", "which sets should I see", "build my festival schedule",
  or shares a festival lineup/schedule image and wants help deciding who to see.
---

# Festival Planner

Build a prioritized, conflict-resolved festival day plan by cross-referencing the user's
Tidal library with the festival schedule, applying taste preferences, incorporating friend
plans, and respecting venue geography.

## Inputs

Gather these before building a plan. Ask for anything missing.

1. **Schedule image(s)** -- stage/time grid for the day. Parse carefully: artist, stage, start time, end time.
2. **Venue map** -- stage locations and relative distances. Essential for realistic transitions.
3. **Friend plans** (optional) -- screenshots from OneSetlist or similar tools. Note which friends are at which sets.
4. **User overrides** -- any "must-see" or "skip" artists stated explicitly. These are top priority.
5. **Previous day highlights** -- ask what the user loved from earlier days. Surprise discoveries (e.g. Creepy Nuts on Friday) inform taste for remaining days.

## Process

### Step 1: Parse the Schedule

Extract every artist, stage, start time, and end time from the schedule image.
Double-check stage assignments -- do NOT assume artists on the same row are on the same stage.
Cross-reference with the lineup image if available.

### Step 2: Pull Tidal Data

Use the Tidal skill to gather affinity signals. Write a one-off Python script for bulk operations.

**Affinity signals (strongest to weakest):**
1. **User explicitly stated priority** -- always #1
2. **Followed artist** -- user follows them on Tidal
3. **Liked tracks** -- tracks from the artist appear in user's favorites
4. **In curated playlists** -- artist appears in recommendation/curated playlists (e.g. "CLAW Recs")
5. **In liked/year playlists** -- artist appears in "Liked 2026" or similar year playlists
6. **In festival schedule playlist** -- tracks exist in the day's schedule playlist (e.g. "Coachella 2026 Friday")
7. **Taste profile match** -- artist fits the user's taste from USER.md but no direct library signal

**Data to fetch:**
- User's followed artists (check which Friday artists are followed)
- Festival schedule playlist tracks (grouped by artist)
- Curated recs playlist tracks (grouped by artist)
- Year-based liked playlists (check for artist presence)
- User's favorite/liked tracks (check if any festival playlist tracks are liked)

Reference `skills/tidal/SKILL.md` for API patterns. Use `login_session_file()` for auth.

### Step 3: Score Each Artist

For each artist on the day's schedule, assign an affinity tier:

- **S tier**: User override / must-see
- **A tier**: Followed + liked tracks + in recs/liked playlists (multiple signals)
- **B tier**: Followed OR multiple playlist appearances
- **C tier**: Single playlist appearance or strong taste match
- **D tier**: In schedule playlist only (top tracks, no other signal)
- **Unranked**: No library signal, weak taste match

### Step 4: Apply Taste Profile

Read USER.md for taste preferences. Key dimensions:
- Genre affinities (Latin, electronic/hyperpop, indie/alt, Afrobeats, punk, etc.)
- Specific artist comparisons (if artist X is similar to followed artists)
- **Latin influence is a strong positive signal** for this user specifically
- **Previous day highlights matter.** If the user loved an unexpected act (different genre, new discovery), factor that into remaining days. Real-time taste > static profile.

Use taste profile to break ties and elevate C-tier artists that strongly match.

### Step 5: Map Friend Overlap

If friend plans are provided:
- Note which friends are at which sets
- For slots where the user has weak preference (C/D tier), prefer sets where friends (especially named close friends) will be
- Flag "whole group" convergence points -- these are social anchors

### Step 6: Build the Schedule

**Hard rules:**
- **No partial sets under 30 minutes.** Either commit to a set or skip it entirely.
- **Account for walking time** between stages. Use the venue map. Budget 5-15 min depending on distance.
- **Include at least one food/hydration break** of 30+ min, ideally before sunset.
- **Arrive early for #1 priority** -- ask the user how early they want to be. Can be 40-60 min. Work backward from that to determine when to leave the preceding set.
- **Full sets for S and A tier artists.** Only consider leaving early for B tier and below.
- **Optional/flexible sets are valid.** Mark sets as "optional" or "vibe check" when the user has mild interest but doesn't want a hard commitment (e.g. guest watch, vibes check). These can be cut short without guilt. Label them clearly in the schedule. Limit to 2-3 per day max -- too many options makes the plan stressful instead of freeing.
- **"Posted at venue" time is real.** When the user wants to arrive very early for their top pick, schedule explicit chill/hold-spot time at that stage. This is not dead time -- it's part of the plan.

**Conflict resolution:**
- When two high-tier artists overlap, pick the one with more affinity signals.
- If tied on signals, prefer: rarer live act > stronger taste match > friend overlap.
- **Solo vs. group context matters.** If the user is attending with friends, sets where friends converge are worth more than solo discoveries. A B-tier artist with the whole crew beats an A-tier artist alone -- unless the user says otherwise. Ask who they're going with and who they want to spend time with.
- **Rarity matters.** Older/legacy artists who may not tour again (David Byrne, Devo) should be weighted higher than acts that tour regularly (Interpol, Disclosure), even if the touring act has more playlist signals.
- Present the conflict and reasoning to the user -- don't silently drop artists.

**Schedule structure:**
- Present as a clean timeline: time, artist, stage
- Note transitions (walk from X to Y)
- Mark breaks explicitly
- Flag any sacrifices and why
- **Include short descriptions** of each artist (genre, vibe, why they're picked) plus alternatives for weak-signal picks
- When the user says "non-negotiable", lock those slots immediately and build around them

### Step 7: Validate (Map Pass)

Before presenting, trace EVERY transition against the venue map:
- Calculate walking time between each consecutive pair of stages
- If gap between sets < walking time, flag it and adjust (leave early or arrive late)
- No impossible stage transitions (back-to-back at distant stages with 0 min gap)
- No phantom partial sets crept in
- S-tier artists all have full sets
- At least one real break exists
- The plan accounts for arrival and departure times
- **Run the map check on the first draft, not as an afterthought.** Don't present a plan then fix geography later.

## Conventions

- Always parse schedule images yourself -- don't rely on prior assumptions about stage/time assignments
- Present affinity reasoning transparently ("you follow them", "3 liked tracks", "fits your Latin electronic taste")
- When the user corrects a stage/time reading, re-verify the full schedule
- Don't pad with "good acts" that have no library signal -- every pick needs a reason
- Ask about friend plans proactively if not provided
- If the user says "I want to arrive early for X", adjust the preceding slot accordingly
- Latin influence preference is documented in USER.md -- apply it as a tiebreaker
- **Multi-day fatigue is real.** By day 3, legs are wrecked. Favor same-stage camping (back-to-back acts at one stage) over ambitious cross-venue routes. Longer food breaks too.
- **"Already seen" matters.** If the user has seen an artist before (at a previous festival, tour, etc.), deprioritize them in favor of fresh acts unless the user says otherwise.
- **On-the-fly questions during the festival** ("X vs Y?") -- give a quick decisive answer with reasoning. Don't re-run the full scoring process. The user is standing in a field, not sitting at a desk.
- **When presenting the final schedule, ask if the user wants cron reminders set up** (15 min before each set via openclaw cron).

## Festival-Specific Notes

### Coachella 2026

- Schedule playlists: "Coachella 2026 Friday" / "Saturday" / "Sunday"
- Curated recs: "Coachella 2026 CLAW Recs"
- Reference playlist (artist IDs): "Coachella 2024 Curated Playlist"
- Quasar and Sahara are on opposite far ends of the venue -- transitions between them take 15+ min
- Coachella Stage is northwest, Mojave/Gobi are center, Sonora is center-north
- Outdoor Theatre is west, between Coachella Stage and Mojave
- Yuma is south-center
- Do Lab is center-south near Sonora area
- **Sahara <-> Coachella Stage is the longest walk on the grounds (15+ min).** Avoid back-to-back between these two unless there's a 20+ min gap.
- **Gobi <-> Gobi back-to-back is the dream.** Same-stage camping eliminates walking and is especially valuable on day 3.
- **Mojave <-> Gobi are adjacent** -- 2 min walk. Treat as one zone.
- Desert heat: emphasize hydration breaks especially before 6 PM
- Cron reminders: use `openclaw cron add --at <ISO time> --tz America/Los_Angeles --announce --channel telegram:<chat-id> --delete-after-run --light-context` for one-shot set reminders (15 min before each set)
- Sunday ends at midnight (not 1am like Fri/Sat) -- plan accordingly
- Record Safari near Coachella Stage sells past-year merch and vinyl

### Coachella 2026 Highlights (for future reference)

Friday highlights: Not for Radio (#1), Creepy Nuts (surprise discovery), Carolina Durante, Cachirula
Saturday highlights: Jack White, rusowsky, Nine Inch Nails, David Byrne
Sunday: COBRAH, Oklou, FKA twigs, KAROL G (closers)
