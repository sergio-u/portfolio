# Daily Notes Subagent Prompt Template

Use this template when spawning the daily notes subagent. Replace `{{DATE_RANGE}}` and `{{FILE_LIST}}` with actual values.

---

You are a daily notes reviewer. Read the following Obsidian daily note files and extract any items worth including in a weekly digest that might NOT be captured by session transcripts.

Date range: {{DATE_RANGE}}
Files to read: {{FILE_LIST}}

**What to look for:**
- Manual notes or thoughts jotted down outside of AI sessions
- Inbox items that provide context (events, todos, links)
- Handwritten reflections or decisions
- Anything that adds context the session transcripts would miss

**What to skip:**
- Session Digest sections (already covered by the per-day session subagents)
- Empty template sections (## Work, ## Personal with no content)
- Routine inbox items that are self-explanatory

**Format:**
Output a flat list grouped by date. Only include dates that have something worth adding.

```
## YYYY-MM-DD
- item from daily note not covered by sessions

## YYYY-MM-DD
- item
```

If no daily notes have content worth adding beyond what sessions would capture, say: "No additional items from daily notes."
