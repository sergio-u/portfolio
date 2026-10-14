---
name: knowledge-base
user-invocable: false
description: >
  Query the AnythingLLM knowledge base (RAG) for information from uploaded documents, notes,
  and reference materials. Use when the user asks questions that might be answered by their
  personal knowledge base, second brain, or uploaded documents. Triggers on "knowledge base",
  "kb", "search my documents", "check my notes", "what do my docs say about".
---

# Knowledge Base (AnythingLLM)

Query the self-hosted AnythingLLM instance for RAG-powered answers with source attribution.

## Execution

```bash
curl -s -X POST "$ANYTHINGLLM_HOST/api/v1/workspace/my-workspace/chat" \
  -H "Authorization: Bearer $ANYTHINGLLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message": "<question>", "mode": "query"}'
```

Default workspace: `my-workspace`.

### Chat (primary)

**Parameters:**
- `message` (required) -- the question
- `mode` (required) -- `"query"` (documents only, default), `"chat"` (documents + LLM knowledge), or `"automatic"` (tool-calling if provider supports it)
- `sessionId` (optional) -- partition chats by an external ID for conversation continuity without creating threads
- `attachments` (optional) -- array of `{name, mime, contentString}` for images or documents

**Response:** `textResponse` contains the answer, `sources[]` contains `{title, chunk, score}` for citations. If `type` is `"abort"`, the query failed.

## Vector Search (raw document lookup)

Direct vector similarity search without LLM processing -- returns raw matching chunks. Use when you need the source text itself rather than an LLM-synthesized answer.

```bash
curl -s -X POST "$ANYTHINGLLM_HOST/api/v1/workspace/my-workspace/vector-search" \
  -H "Authorization: Bearer $ANYTHINGLLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "<search terms>", "topN": 4, "scoreThreshold": 0.5}'
```

Returns `results[]` with `{id, text, metadata: {title, url, chunkSource}}`.

## Other Endpoints

All use the same auth header.

- **Thread chat:** `POST /api/v1/workspace/{slug}/thread/{thread-slug}/chat` -- isolated conversation thread
- **New thread:** `POST /api/v1/workspace/{slug}/thread/new`
- **List workspaces:** `GET /api/v1/workspaces`
- **Workspace details:** `GET /api/v1/workspace/{slug}`
- **List documents:** `GET /api/v1/documents`
- **Upload document:** `POST /api/v1/document/upload` (multipart/form-data, field: `file`)
- **Upload link:** `POST /api/v1/document/upload-link` -- scrape a URL and prepare for embedding

## Conventions

- Default to `mode: "query"` always. Only use `"chat"` if the user explicitly asks.
- Use `vector-search` when the user wants raw source text rather than a synthesized answer
- Cite sources in the response: mention document title and relevant snippet
- If sources are empty in query mode, tell the user no matching documents were found
- If `textResponse` is null or `type` is `"abort"`, report the error

## Authentication

Env vars loaded from `~/.openclaw/.env`:

- `ANYTHINGLLM_HOST` -- base URL of the AnythingLLM instance
- `ANYTHINGLLM_API_KEY` -- API key for all requests (passed as `Authorization: Bearer`)

## Document Management

Self-contained CLI for managing documents in AnythingLLM:

```bash
uv run skills/knowledge-base/scripts/kb_docs.py <command> [args]
```

### Commands

```bash
kb_docs.py list [--folder NAME]                     # List all documents or a folder
kb_docs.py upload <file> [--folder NAME] [--auto-embed]  # Upload a file
kb_docs.py upload-link <url> [--auto-embed]          # Scrape a URL
kb_docs.py raw-text <title> <text> [--auto-embed]    # Upload raw text (use - for stdin)
kb_docs.py embed <doc-location>                      # Add parsed doc to workspace
kb_docs.py unembed <doc-location>                    # Remove doc from workspace
kb_docs.py delete <doc-location>                     # Permanently delete from system
kb_docs.py filetypes                                 # Show accepted file types
```

All commands accept `--workspace SLUG` (default: `my-workspace`).

### Upload + Embed flow

Uploading parses the file. Embedding adds it to the vector store for RAG queries. Use `--auto-embed` to do both in one step:

```bash
kb_docs.py upload /path/to/file.md --auto-embed
```

Without `--auto-embed`, you must embed separately using the `location` from the upload response:

```bash
kb_docs.py embed "custom-documents/file.md-uuid.json"
```

For raw text (e.g., piping content):

```bash
echo "Content here" | kb_docs.py raw-text "My Document Title" - --auto-embed
```
