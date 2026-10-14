#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""
AnythingLLM Document Manager CLI.

Commands:
  list                          List all documents (or in a folder)
  upload <file>                 Upload a file to be parsed
  upload-link <url>             Scrape a URL and prepare for embedding
  raw-text <title> <text>       Upload raw text content directly
  embed <doc-location>          Add a parsed document to a workspace
  unembed <doc-location>        Remove a document from a workspace
  delete <doc-location>         Permanently remove a document from the system
  filetypes                     Show accepted file types

Common flags:
  --workspace SLUG              Target workspace (default: my-workspace)
  --folder NAME                 Target folder for upload/list
  --auto-embed                  Automatically embed into workspace after upload
"""

import argparse
import os
import json
import sys
from pathlib import Path

import requests

CONFIG = {
    "host": os.environ.get("ANYTHINGLLM_HOST", "http://localhost:3001"),
    "api_key": os.environ["ANYTHINGLLM_API_KEY"],
    "default_workspace": "my-workspace",
}

def api(method, path, **kwargs):
    """Make an API request."""
    url = f"{CONFIG['host']}/api{path}"
    headers = {"Authorization": f"Bearer {CONFIG['api_key']}"}
    if "headers" in kwargs:
        headers.update(kwargs.pop("headers"))
    resp = getattr(requests, method)(url, headers=headers, **kwargs)
    if resp.status_code == 403:
        print(json.dumps({"ok": False, "error": "Invalid API key"}))
        sys.exit(1)
    return resp.json()


def cmd_list(args):
    """List all documents or documents in a specific folder."""
    if args.folder:
        data = api("get", f"/v1/documents/folder/{args.folder}")
        docs = data.get("documents", [])
    else:
        data = api("get", "/v1/documents")
        items = data.get("localFiles", {}).get("items", [])
        docs = []
        for item in items:
            if item["type"] == "folder":
                docs.append({"name": item["name"], "type": "folder",
                             "count": len(item.get("items", []))})
                for sub in item.get("items", []):
                    docs.append({"name": sub["name"], "type": "file",
                                 "folder": item["name"],
                                 "title": sub.get("title", ""),
                                 "cached": sub.get("cached", False)})
            else:
                docs.append({"name": item["name"], "type": "file",
                             "title": item.get("title", ""),
                             "cached": item.get("cached", False)})
    print(json.dumps({"ok": True, "documents": docs}, indent=2))


def cmd_upload(args):
    """Upload a file to AnythingLLM."""
    filepath = Path(args.file)
    if not filepath.exists():
        print(json.dumps({"ok": False, "error": f"File not found: {filepath}"}))
        sys.exit(1)

    files = {"file": (filepath.name, open(filepath, "rb"))}
    form_data = {}
    if args.auto_embed:
        form_data["addToWorkspaces"] = args.workspace

    if args.folder:
        data = api("post", f"/v1/document/upload/{args.folder}", files=files, data=form_data)
    else:
        data = api("post", "/v1/document/upload", files=files, data=form_data)

    if data.get("success"):
        docs = data.get("documents", [])
        result = {"ok": True, "uploaded": len(docs), "documents": docs}
        if args.auto_embed:
            result["embedded_to"] = args.workspace
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps({"ok": False, "error": data.get("error", "Upload failed")}))


def cmd_upload_link(args):
    """Scrape a URL and prepare for embedding."""
    payload = {"link": args.url}
    if args.auto_embed:
        payload["addToWorkspaces"] = args.workspace

    data = api("post", "/v1/document/upload-link", json=payload)

    if data.get("success"):
        docs = data.get("documents", [])
        result = {"ok": True, "uploaded": len(docs), "documents": docs}
        if args.auto_embed:
            result["embedded_to"] = args.workspace
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps({"ok": False, "error": data.get("error", "Upload failed")}))


def cmd_raw_text(args):
    """Upload raw text content directly."""
    payload = {
        "textContent": args.text,
        "metadata": {"title": args.title},
    }
    if args.auto_embed:
        payload["addToWorkspaces"] = args.workspace

    data = api("post", "/v1/document/raw-text", json=payload)

    if data.get("success"):
        docs = data.get("documents", [])
        result = {"ok": True, "uploaded": len(docs), "documents": docs}
        if args.auto_embed:
            result["embedded_to"] = args.workspace
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps({"ok": False, "error": data.get("error", "Upload failed")}))


def cmd_embed(args):
    """Add a document to a workspace (update-embeddings with adds)."""
    data = api("post", f"/v1/workspace/{args.workspace}/update-embeddings",
               json={"adds": [args.doc_location], "deletes": []})

    workspace = data.get("workspace", {})
    print(json.dumps({"ok": True, "workspace": workspace.get("name", args.workspace),
                       "action": "embedded", "document": args.doc_location}))


def cmd_unembed(args):
    """Remove a document from a workspace (update-embeddings with deletes)."""
    data = api("post", f"/v1/workspace/{args.workspace}/update-embeddings",
               json={"adds": [], "deletes": [args.doc_location]})

    workspace = data.get("workspace", {})
    print(json.dumps({"ok": True, "workspace": workspace.get("name", args.workspace),
                       "action": "unembedded", "document": args.doc_location}))


def cmd_delete(args):
    """Permanently remove documents from the system."""
    data = api("delete", "/v1/system/remove-documents",
               json={"names": [args.doc_location]})

    if data.get("success"):
        print(json.dumps({"ok": True, "action": "deleted", "document": args.doc_location}))
    else:
        print(json.dumps({"ok": False, "error": data.get("message", "Delete failed")}))


def cmd_filetypes(args):
    """Show accepted file types."""
    data = api("get", "/v1/document/accepted-file-types")
    print(json.dumps({"ok": True, "types": data.get("types", {})}))


def main():
    parser = argparse.ArgumentParser(description="AnythingLLM Document Manager")
    parser.add_argument("--workspace", default=CONFIG["default_workspace"],
                        help="Target workspace slug")
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    p = sub.add_parser("list", help="List documents")
    p.add_argument("--folder", help="List documents in a specific folder")

    # upload
    p = sub.add_parser("upload", help="Upload a file")
    p.add_argument("file", help="Path to file")
    p.add_argument("--folder", help="Upload to a specific folder")
    p.add_argument("--auto-embed", action="store_true",
                   help="Automatically embed into workspace after upload")

    # upload-link
    p = sub.add_parser("upload-link", help="Scrape a URL")
    p.add_argument("url", help="URL to scrape")
    p.add_argument("--auto-embed", action="store_true",
                   help="Automatically embed into workspace after upload")

    # raw-text
    p = sub.add_parser("raw-text", help="Upload raw text content")
    p.add_argument("title", help="Document title")
    p.add_argument("text", help="Text content (use - for stdin)")
    p.add_argument("--auto-embed", action="store_true",
                   help="Automatically embed into workspace after upload")

    # embed
    p = sub.add_parser("embed", help="Add a document to a workspace")
    p.add_argument("doc_location", help="Document location (e.g. custom-documents/file.json)")

    # unembed
    p = sub.add_parser("unembed", help="Remove a document from a workspace")
    p.add_argument("doc_location", help="Document location")

    # delete
    p = sub.add_parser("delete", help="Permanently remove a document from the system")
    p.add_argument("doc_location", help="Document location (e.g. custom-documents/file.json)")

    # filetypes
    sub.add_parser("filetypes", help="Show accepted file types")

    args = parser.parse_args()

    # Handle stdin for raw-text
    if hasattr(args, "text") and args.text == "-":
        args.text = sys.stdin.read()

    commands = {
        "list": cmd_list,
        "upload": cmd_upload,
        "upload-link": cmd_upload_link,
        "raw-text": cmd_raw_text,
        "embed": cmd_embed,
        "unembed": cmd_unembed,
        "delete": cmd_delete,
        "filetypes": cmd_filetypes,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
