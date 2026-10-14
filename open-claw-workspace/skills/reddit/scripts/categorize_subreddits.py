#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Categorize audited subreddits into broad themes for multireddit creation."""

import argparse
import json
import sys
from typing import Any

CATEGORIES: dict[str, list[str]] = {
    "tech_programming": [
        "programming", "code", "coding", "developer", "software", "algorithm",
        "python", "javascript", "typescript", "rust", "golang", "ruby", "java",
        "csharp", "c++", "cpp", "dart", "crystal", "haskell", "lisp", "elixir",
        "swift", "kotlin", "flutter", "react", "vue", "angular", "svelte",
        "webdev", "frontend", "backend", "fullstack", "api", "graphql",
        "compiler", "interpreter", "git", "vim", "neovim", "emacs", "ide",
        "vscode", "jetbrains", "database", "sql", "nosql", "redis", "postgres",
    ],
    "tech_ai_ml": [
        "ai ", "artificial intelligence", "machine learning", "deep learning",
        "neural", "llm", "gpt", "chatgpt", "claude", "anthropic", "openai",
        "copilot", "codex", "agent", "agi", "singularity", "transformer",
        "reinforcement learning", "nlp", "computer vision", "diffusion",
        "stable diffusion", "midjourney", "generative",
    ],
    "tech_infra_devops": [
        "linux", "arch", "ubuntu", "debian", "fedora", "nixos", "centos",
        "docker", "kubernetes", "terraform", "ansible", "aws", "azure", "gcp",
        "cloud", "devops", "sysadmin", "networking", "homelab", "selfhost",
        "server", "ci/cd", "jenkins", "github actions", "wsl",
    ],
    "tech_gadgets": [
        "android", "iphone", "apple", "pixel", "samsung", "tablet",
        "headphone", "earbuds", "airpods", "smartwatch", "wearable",
        "keyboard", "mechanical keyboard", "mouse", "monitor", "display",
        "laptop", "pc build", "buildapc", "hardware", "3d print",
        "vr", "xr", "ar ", "oculus", "quest",
    ],
    "gaming": [
        "game", "gaming", "xbox", "playstation", "nintendo", "switch",
        "steam", "pc gaming", "rpg", "mmorpg", "fps", "indie game",
        "retro gaming", "emulator", "emulation", "speedrun", "esport",
        "zelda", "mario", "pokemon", "souls", "elden ring",
        "cyberpunk", "assassin", "beat saber",
    ],
    "music_audio": [
        "music", "hiphop", "hip hop", "rap", "electronic", "edm",
        "techno", "house", "drum and bass", "dnb", "dubstep", "breakbeat",
        "breakcore", "ambient", "jazz", "classical", "rock", "metal",
        "punk", "pop", "indie", "folk", "latin", "cumbia", "reggaeton",
        "city pop", "synthwave", "vaporwave", "lo-fi", "lofi",
        "guitar", "piano", "synthesizer", "production", "ableton",
        "audio engineering", "audiophile", "headphones", "vinyl",
        "spotify", "bandcamp", "soundcloud", "dj", "rave",
        "daft punk", "arca",
    ],
    "mental_health": [
        "adhd", "anxiety", "depression", "therapy", "cptsd", "ptsd",
        "bpd", "borderline", "ocd", "bipolar", "mental health",
        "counseling", "psychiatry", "anhedonia", "brain fog",
        "neurodivergent", "autism", "asd",
    ],
    "philosophy_spirituality": [
        "philosophy", "philosopher", "stoic", "existential", "nihil",
        "buddhism", "buddhist", "meditation", "mindfulness", "zen",
        "taoism", "dharma", "consciousness", "psychedelic",
        "critical theory", "ontology", "epistemology", "ethics",
        "theology", "religion", "spiritual",
    ],
    "food_cooking": [
        "cooking", "food", "recipe", "baking", "bread", "sourdough",
        "coffee", "tea", "cocktail", "wine", "beer", "ferment",
        "meal prep", "nutrition", "diet", "culinary", "restaurant",
        "sardine", "seafood", "vegan", "vegetarian",
    ],
    "productivity": [
        "productivity", "bullet journal", "bujo", "planner",
        "getting things done", "gtd", "notion", "obsidian",
        "roam", "logseq", "pkm", "second brain", "zettelkasten",
        "time management", "habit", "self improvement", "self discipline",
        "organization", "todo", "task management", "clickup", "marvin",
    ],
    "books_reading": [
        "book", "reading", "literature", "novel", "fiction",
        "sci-fi", "fantasy", "audiobook", "kindle", "ebook",
        "library", "sanderson", "cosmere", "asimov", "lovecraft",
    ],
    "science": [
        "science", "physics", "biology", "chemistry", "astronomy",
        "space", "neuroscience", "cognitive", "research",
        "mathematics", "math", "statistics",
    ],
    "fitness_health": [
        "fitness", "gym", "workout", "exercise", "running",
        "bodyweight", "yoga", "stretch", "nutrition",
        "weight loss", "strength", "cardio", "sleep",
        "health", "supplement", "vitamin", "chronic fatigue",
    ],
    "finance": [
        "finance", "investing", "stock", "crypto", "bitcoin",
        "ethereum", "budget", "frugal", "credit card", "churning",
        "fire", "retirement", "tax", "real estate",
    ],
    "tv_film": [
        "tv", "television", "netflix", "hbo", "hulu",
        "disney+", "movie", "film", "cinema", "director",
        "series", "season", "episode", "streaming",
    ],
    "art_design": [
        "art", "design", "illustration", "graphic", "typography",
        "photography", "cinematography", "animation", "pixel art",
        "wallpaper", "aesthetic", "creative",
    ],
    "social_culture": [
        "politics", "news", "culture", "society",
        "relationship", "dating", "advice", "askreddit",
        "ask men", "ask women", "life pro tips",
    ],
}

MIN_CATEGORY_SIZE = 10
MAX_MULTIREDDIT_SIZE = 100


def score_sub(
    name: str, title: str, description: str, hints: list[str],
    categories: dict[str, list[str]],
) -> dict[str, int]:
    text = f"{name} {title} {description}".lower()
    scores: dict[str, int] = {}
    # Hints get high priority
    for hint in hints:
        if hint == "tv_show":
            scores["tv_film"] = scores.get("tv_film", 0) + 10
        elif hint == "anime":
            scores["tv_film"] = scores.get("tv_film", 0) + 5
    for cat, keywords in categories.items():
        for kw in keywords:
            if kw in text:
                scores[cat] = scores.get(cat, 0) + 1
    return scores


def categorize(audit_report: dict[str, Any]) -> dict[str, Any]:
    assignments: dict[str, list[str]] = {cat: [] for cat in CATEGORIES}
    assignments["uncategorized"] = []

    for sub in audit_report["subreddits"]:
        if sub["status"] != "accessible":
            continue
        name = sub["name"]
        title = sub.get("title", "")
        desc = sub.get("public_description", "")
        hints = sub.get("category_hints", [])
        scores = score_sub(name, title, desc, hints, CATEGORIES)
        if scores:
            best = max(scores, key=lambda k: scores[k])
            assignments[best].append(name)
        else:
            assignments["uncategorized"].append(name)

    # Merge small categories into uncategorized
    for cat in list(assignments):
        if cat == "uncategorized":
            continue
        if len(assignments[cat]) < MIN_CATEGORY_SIZE:
            assignments["uncategorized"].extend(assignments[cat])
            del assignments[cat]

    # Split large categories
    final: dict[str, dict[str, Any]] = {}
    for cat, subs in assignments.items():
        if not subs:
            continue
        subs.sort(key=str.lower)
        if len(subs) <= MAX_MULTIREDDIT_SIZE:
            final[cat] = {
                "display_name": cat.replace("_", " ").title(),
                "subreddits": subs,
                "count": len(subs),
            }
        else:
            for chunk_i in range(0, len(subs), MAX_MULTIREDDIT_SIZE):
                chunk = subs[chunk_i:chunk_i + MAX_MULTIREDDIT_SIZE]
                part = chunk_i // MAX_MULTIREDDIT_SIZE + 1
                key = f"{cat}_{part}"
                final[key] = {
                    "display_name": f"{cat.replace('_', ' ').title()} {part}",
                    "subreddits": chunk,
                    "count": len(chunk),
                }

    return {"categories": final}


def main() -> None:
    p = argparse.ArgumentParser(description="Categorize subreddits from audit report.")
    p.add_argument("--input", required=True, help="Audit report JSON")
    p.add_argument("--output", required=True, help="Output categorized JSON")
    args = p.parse_args()

    with open(args.input) as f:
        audit = json.load(f)

    result = categorize(audit)

    with open(args.output, "w") as f:
        json.dump(result, f, indent=2)

    print("Categories:", file=sys.stderr)
    for cat, data in sorted(result["categories"].items()):
        print(f"  {data['display_name']}: {data['count']} subs", file=sys.stderr)


if __name__ == "__main__":
    main()
