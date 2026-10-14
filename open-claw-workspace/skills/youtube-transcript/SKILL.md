---
name: youtube-transcript
description: >
  Fetch transcripts/captions from YouTube videos using youtube-transcript-api.
  Use when the user says "get transcript", "what does this video say", "YouTube captions",
  "video transcript", or shares a YouTube link and wants the transcript, subtitles,
  or a summary of what was said in the video.
---

# YouTube Transcript

## Execution

```bash
uv run skills/youtube-transcript/fetch_transcript.py <video_url_or_id>
```

Accepts full YouTube URLs (`youtube.com/watch?v=...`, `youtu.be/...`, `youtube.com/shorts/...`) or bare video IDs.

### Output formats

- `--output-format text` (default) -- plain concatenated transcript text with a metadata header
- `--output-format timestamped` -- each snippet prefixed with `[MM:SS]` timestamps
- `--output-format json` -- full structured data with metadata and individual snippets (text, start, duration)

### Optional flags

- `--languages en es de ...` -- language priority list (default: `en`). Tries each in order.
- `--translate LANG` -- translate the transcript to a target language code (e.g. `es`, `fr`, `ja`)
- `--list-transcripts` -- list available transcripts/languages for the video instead of fetching one
- `--preserve-formatting` -- keep HTML formatting (bold, italic) in transcript text

## Conventions

- Default invocation (no flags) gets the English transcript as plain text. This is correct for most requests.
- Use `--output-format timestamped` when the user wants to reference specific moments in the video.
- Use `--output-format json` when you need snippet-level timing data or machine-readable output for parsing.
- Use `--list-transcripts` first if the user asks for a non-English transcript and you're unsure what's available.
- Use `--translate` when the transcript isn't available in the desired language but translation is supported.
- Present the transcript as a readable summary unless the user asks for the raw text.
- Confirm before fetching transcripts for many videos in bulk.
- Summarize results cleanly -- provide key points from the transcript rather than dumping raw text.
- If the request fails with an IP block error, inform the user that YouTube is blocking requests from this server -- it's a known limitation with cloud-hosted IPs.
- If no transcript exists (e.g. no captions on the video), tell the user the video doesn't have captions available.

## Requirements

- `uv` must be installed (script dependencies are managed inline via uv).
