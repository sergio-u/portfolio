# Extract Subagent Prompt Template

Use this template when spawning extraction subagents. Replace `{TYPE}`, `{ITEMS_JSON}`, and `{TYPE_INSTRUCTIONS}` before passing as the task.

---

You are an extraction subagent. Your job is to extract readable content from a batch of Instapaper bookmarks.

## Input

Source type: {TYPE}
Bookmarks to extract:

{ITEMS_JSON}

## Instructions

{TYPE_INSTRUCTIONS}

## Output

Write results to `/tmp/instapaper-extracted-{TYPE}.json` as a JSON array:

```json
[
  {
    "bookmark_id": 12345,
    "title": "Article Title",
    "url": "https://...",
    "source_type": "{TYPE}",
    "method": "instapaper|trafilatura|hackernews|reddit|youtube",
    "status": "ok|partial|failed",
    "content": "extracted text...",
    "char_count": 1234,
    "discussion": "optional, HN/reddit community discussion summary"
  }
]
```

- `status`: "ok" if char_count >= 200, "partial" if < 200, "failed" if 0 or error
- `content`: the main article/post text (max 5000 chars)
- `discussion`: only for hackernews and reddit -- a brief summary of community comments

Process all items. Do not skip any.

**Write the output file incrementally.** Rewrite the full JSON array after *each*
item, starting with the first. Subagents on this workflow crash mid-task regularly;
chunks that buffered all output until the end lost 100% of their work, while chunks
writing after each item lost nothing. Never batch the write to the end.

**Report honestly.** Never claim an item succeeded unless its extracted text is
actually in the file. A false "all 13 extracted cleanly" report costs far more than an
honest partial result, because the parent has to re-verify everything.

**Before completing:** Verify your output file exists and contains valid JSON:
```bash
python3 -c "import json; data=json.load(open('/tmp/instapaper-extracted-{TYPE}.json')); print(f'{len(data)} items written')"
```
Do NOT declare completion until this verification passes.

---

## Type-specific instructions

### For articles:

```
For each bookmark, run:

cd ~/.openclaw/workspace
source ~/.openclaw/.env 2>/dev/null
export INSTAPAPER_KEY INSTAPAPER_SECRET INSTAPAPER_USER INSTAPAPER_PASS
uv run skills/instapaper/scripts/fetch_and_extract.py "URL" --bookmark-id BOOKMARK_ID --max-chars 5000

This handles the fallback chain (Instapaper get_text -> trafilatura) automatically.
If the result has status "defer_youtube", the page is a YouTube-embed wrapper:
- First try extracting the transcript via youtube-transcript skill using the `youtube_url` field.
- If the transcript extraction fails (no transcript available, error, etc.), fall back to using the `content` field
  from the fetch_and_extract response if it has >200 chars -- this is the article text around the embed.
- Only mark as failed if BOTH the transcript AND the article content are unavailable.

For pointer/aggregator pages: if the extraction returns <200 chars and the content contains an outbound
link to a different domain, follow that link and re-extract using fetch_and_extract on the target URL.
```

### For hackernews:

```
For each bookmark, do TWO extractions:

1. Comments: Run from workspace root:
   uv run skills/hackernews/scripts/fetch_post.py "URL" --max-comments 30 --depth 2

2. Linked article: The response has a "url" field pointing to the external article.
   Extract it WITHOUT --bookmark-id:
   cd ~/.openclaw/workspace
   source ~/.openclaw/.env 2>/dev/null
   export INSTAPAPER_KEY INSTAPAPER_SECRET INSTAPAPER_USER INSTAPAPER_PASS
   uv run skills/instapaper/scripts/fetch_and_extract.py "LINKED_URL" --max-chars 5000

   Do NOT pass --bookmark-id for HN bookmarks. Instapaper's cached text for an HN
   bookmark is the comment page, not the linked article, and it is long enough to
   pass as a valid extraction. fetch_and_extract.py now guards against this, but
   passing the linked URL without the bookmark id is still the correct call.

   Sanity check: if content begins like "NNN points by <user> ... | hide | past |
   favorite", it is the HN page, not the article. Re-extract.

Combine both: put the article text in "content" and a summary of the HN discussion in "discussion".
If the HN post is a self-post (no external URL), just use the post text as content.
```

### For reddit:

```
For each bookmark, run from workspace root:
   uv run skills/reddit/scripts/fetch_post.py "URL" --max-comments 30 --depth 2 --min-score 2

The post body + comments ARE the content. Put the post body in "content" and a summary of the top comments in "discussion".
```

### For youtube:

```
Read the youtube-transcript skill first at ~/.openclaw/workspace/skills/youtube-transcript/SKILL.md.
For each bookmark, use the skill to fetch the transcript.
Put the transcript text in "content". No "discussion" field needed.
```
