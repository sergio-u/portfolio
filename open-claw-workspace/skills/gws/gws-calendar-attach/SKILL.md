---
name: gws-calendar-attach
description: "Google Calendar: Attach Drive files (tickets, receipts, docs) to existing events."
user-invocable: false
---

# calendar attach recipe

Attach a Drive file to a Google Calendar event. Use when the user provides a ticket image, receipt, or document to attach.

The `+insert` shortcut does not support attachments — create the event first (via `gws calendar +insert` or the raw API), then patch it.

## Pattern

1. Upload the file to Drive (into the standard "Calendar Attachments" folder).
2. Patch the event with `supportsAttachments: true` and the file URL.

## 1. Upload to Drive

Standard destination: the **"Calendar Attachments"** folder (ID: `<folder-id>`).

```bash
# Copy file to workspace first (gws restricts uploads to cwd)
cp /path/to/file.jpg ~/.openclaw/workspace/temp-upload.jpg

gws drive files create \
  --json '{"name": "Event Name - Date.jpg", "parents": ["<folder-id>"]}' \
  --upload temp-upload.jpg \
  --upload-content-type image/jpeg

# Clean up
rm ~/.openclaw/workspace/temp-upload.jpg
```

Capture the returned file `id` for the next step.

## 2. Patch the event

```bash
gws calendar events patch \
  --params '{"calendarId": "primary", "eventId": "EVENT_ID", "supportsAttachments": true}' \
  --json '{"attachments": [{"fileUrl": "https://drive.google.com/file/d/FILE_ID/view", "title": "Descriptive Title", "mimeType": "image/jpeg"}]}'
```

## Notes

- `supportsAttachments: true` is required in the patch params, or attachments are silently ignored.
- Multiple attachments can be included in the `attachments` array.
- This is a **write** command — confirm with the user before executing.

## See Also

- [gws-calendar-insert](../gws-calendar-insert/SKILL.md) — create the event first
- [gws-drive-upload](../gws-drive-upload/SKILL.md) — Drive upload helper
