#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""
One-way sync from Obsidian vault to AnythingLLM.

Compares local vault files against documents already in AnythingLLM,
then uploads new/updated files and embeds them into the workspace.
Uses a content-hash manifest to detect changes efficiently.

Usage:
  uv run skills/knowledge-base/scripts/sync_obsidian.py [--dry-run] [--workspace SLUG] [--folder NAME]
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import requests

# Re-use the API helper and config from kb_docs
sys.path.insert(0, str(Path(__file__).parent))
from kb_docs import api, CONFIG

VAULT_PATH = Path("~/Documents/Sync/Notebook/2026-H1")
MANIFEST_PATH = Path(__file__).parent / ".sync_manifest.json"

# Folders to skip (templates, system config, attachments)
EXCLUDE_DIRS = {".obsidian", "99_System"}


def hash_content(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {}


def save_manifest(manifest: dict):
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))


def scan_vault() -> dict[str, Path]:
    """Return {relative_path: absolute_path} for all .md files in the vault."""
    files = {}
    for md in VAULT_PATH.rglob("*.md"):
        rel = md.relative_to(VAULT_PATH)
        # Skip excluded directories
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        # Skip empty files
        if md.stat().st_size == 0:
            continue
        files[str(rel)] = md
    return files


def get_remote_docs(folder: str) -> dict[str, dict]:
    """Return {relative_vault_path: doc_metadata} for docs in the AnythingLLM folder."""
    data = api("get", "/v1/documents")
    items = data.get("localFiles", {}).get("items", [])
    remote = {}
    prefix = "obsidian://2026-H1/"
    for item in items:
        if item.get("type") != "folder" or item.get("name") != folder:
            continue
        for doc in item.get("items", []):
            # Match on chunkSource or url — both use obsidian:// prefix
            for field in ("chunkSource", "url"):
                val = doc.get(field, "")
                if val.startswith(prefix):
                    remote[val[len(prefix):]] = doc
                    break
    return remote


def upload_doc(rel_path: str, abs_path: Path, folder: str) -> dict | None:
    """Upload a vault file to the AnythingLLM folder with Obsidian metadata."""
    obsidian_url = f"obsidian://2026-H1/{rel_path}"
    metadata = json.dumps({
        "title": abs_path.name,
        "docAuthor": "Obsidian Vault",
        "description": abs_path.name,
        "docSource": "Obsidian Vault",
        "chunkSource": obsidian_url,
    })
    url = f"{CONFIG['host']}/api/v1/document/upload/{folder}"
    headers = {"Authorization": f"Bearer {CONFIG['api_key']}"}
    with open(abs_path, "rb") as f:
        resp = requests.post(url, headers=headers,
                             files={"file": (abs_path.name, f)},
                             data={"metadata": metadata})
    data = resp.json()
    if not data.get("success"):
        print(f"  ERROR uploading {rel_path}: {data.get('error', 'unknown')}", file=sys.stderr)
        return None
    return data.get("documents", [None])[0]


def delete_remote(doc_name: str, folder: str):
    """Remove a document from AnythingLLM."""
    location = f"{folder}/{doc_name}"
    api("delete", "/v1/system/remove-documents", json={"names": [location]})


def embed_docs(doc_locations: list[str], workspace: str):
    """Embed a batch of documents into the workspace."""
    if not doc_locations:
        return
    api("post", f"/v1/workspace/{workspace}/update-embeddings",
        json={"adds": doc_locations, "deletes": []})


def sync(workspace: str, folder: str, dry_run: bool = False):
    vault_files = scan_vault()
    remote_docs = get_remote_docs(folder)
    manifest = load_manifest()

    to_upload: list[str] = []   # new files
    to_update: list[str] = []   # changed files
    unchanged: list[str] = []

    for rel_path, abs_path in vault_files.items():
        content_hash = hash_content(abs_path.read_text(encoding="utf-8"))

        if rel_path not in remote_docs:
            to_upload.append(rel_path)
        elif manifest.get(rel_path) != content_hash:
            to_update.append(rel_path)
        else:
            unchanged.append(rel_path)

    print(f"Vault files:  {len(vault_files)}")
    print(f"Remote docs:  {len(remote_docs)}")
    print(f"New:          {len(to_upload)}")
    print(f"Updated:      {len(to_update)}")
    print(f"Unchanged:    {len(unchanged)}")

    if dry_run:
        if to_upload:
            print("\nWould upload:")
            for p in to_upload:
                print(f"  + {p}")
        if to_update:
            print("\nWould update:")
            for p in to_update:
                print(f"  ~ {p}")
        return

    to_embed: list[str] = []

    # Upload new files
    for rel_path in to_upload:
        abs_path = vault_files[rel_path]
        print(f"  + {rel_path}")
        doc = upload_doc(rel_path, abs_path, folder)
        if doc:
            location = doc.get("location", "")
            if location:
                to_embed.append(location)
            manifest[rel_path] = hash_content(abs_path.read_text(encoding="utf-8"))

    # Update changed files: delete old, re-upload
    for rel_path in to_update:
        abs_path = vault_files[rel_path]
        old_doc = remote_docs[rel_path]
        old_name = old_doc["name"]
        print(f"  ~ {rel_path}")
        # Remove old version
        delete_remote(old_name, folder)
        # Upload new version
        doc = upload_doc(rel_path, abs_path, folder)
        if doc:
            location = doc.get("location", "")
            if location:
                to_embed.append(location)
            manifest[rel_path] = hash_content(abs_path.read_text(encoding="utf-8"))

    # Embed all new/updated docs in one batch
    if to_embed:
        print(f"\nEmbedding {len(to_embed)} documents into '{workspace}'...")
        embed_docs(to_embed, workspace)

    save_manifest(manifest)
    print("Done.")


def main():
    parser = argparse.ArgumentParser(description="Sync Obsidian vault to AnythingLLM")
    parser.add_argument("--workspace", default=CONFIG["default_workspace"],
                        help="Target workspace slug (default: my-workspace)")
    parser.add_argument("--folder", default="obsidian-vault-2026-h1-ea05",
                        help="AnythingLLM folder name for obsidian docs")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without making changes")
    args = parser.parse_args()
    sync(args.workspace, args.folder, args.dry_run)


if __name__ == "__main__":
    main()
