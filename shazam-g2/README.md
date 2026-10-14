# Shazam G2

A song-recognition app for Even Realities G2 smart glasses. Tap, listen for 10 seconds, get the track name, artist, album art, and synced lyrics on your glasses. The sibling app [subtitles-g2](../subtitles-g2/) uses the same SDK for live subtitles.

Built on the raw `@evenrealities/even_hub_sdk` (no `even-toolkit` glass layer) for direct control over the multi-container layout (image, header, and scrolling lyrics), with flicker-free text updates and Floyd-Steinberg dithered album art.

## What it uses

| Piece | Service |
|---|---|
| Recognition | [AudD](https://audd.io) (`api.audd.io`); CORS-open, so it works from a WebView |
| Synced lyrics | [LRCLIB](https://lrclib.net); free, keyless, CORS-open |
| Plain lyrics fallback | [lyrics.ovh](https://api.lyrics.ovh) |
| Album art | AudD-provided Apple Music / Spotify / Deezer CDN URLs |
| Audio capture | G2 glasses microphone via raw SDK `audioControl` (falls back to browser mic for desktop dev) |

## Quick start

### 1. Install

```bash
npm install
```

### 2. Get an AudD API token

Create an account at [dashboard.audd.io](https://dashboard.audd.io), then create `.env.local`:

```bash
cp .env.local.example .env.local
# edit .env.local and set VITE_AUDD_TOKEN=your_token_here
```

AudD also accepts an empty token for about 300 anonymous trial requests, enough to try the app before registering.

### 3. Run the dev server

```bash
npm run dev
```

Open <http://localhost:5173> on your laptop to see the companion UI.

## Running on real glasses

Requires the Even App installed on your phone and paired with the G2 glasses.

```bash
# Terminal 1 — dev server (keep running)
npm run dev

# Terminal 2 — generate a QR code to sideload
npm run qr
```

Scan the QR with the Even App on your phone. The app loads inside the Even App's WebView and pushes UI to the glasses.

Once on your glasses:

| Gesture | Action |
|---|---|
| Tap touchbar | Start recognition from home, re-identify from now playing, or resync after scrolling manually |
| Swipe up/down | Scroll lyrics manually (enters MANUAL mode and pauses auto-sync) |
| Double-tap | Back to idle, or exit from the home screen |

A tap starts listening for 10 seconds, then searching. The now-playing screen shows the title, artist, album art, and lyrics that advance with the music. Swipe to scroll manually; tap to re-lock sync.

## Testing with the simulator (no glasses needed)

The `@evenrealities/evenhub-simulator` mimics the G2 display on your desktop.

```bash
# Terminal 1
npm run dev

# Terminal 2 — list your audio input devices
npx @evenrealities/evenhub-simulator --list-audio-input-devices http://localhost:5173

# Terminal 2 — launch pointing at your preferred mic
npx @evenrealities/evenhub-simulator --aid <device-id> http://localhost:5173
```

### Sending audio from a Mac app (Spotify, Tidal, Apple Music, etc.) using BlackHole

[BlackHole](https://existential.audio/blackhole/) routes system audio into a virtual input device the simulator can consume.

1. Install BlackHole 2ch: `brew install blackhole-2ch`
2. Route your music app to BlackHole:
   - Just Tidal: in Tidal, open Preferences > Streaming > Audio Output Device and pick BlackHole 2ch. Quit and relaunch Tidal if it doesn't appear.
   - Whole system: in System Settings, open Sound > Output and pick BlackHole 2ch. You won't hear anything; create a Multi-Output Device in Audio MIDI Setup if you want both.
3. Find BlackHole's device ID:
   ```bash
   npx @evenrealities/evenhub-simulator --list-audio-input-devices http://localhost:5173
   ```
4. Launch the simulator with it (wrap in quotes because of the colon):
   ```bash
   npx @evenrealities/evenhub-simulator --aid "coreaudio:BlackHole2ch_UID" http://localhost:5173
   ```
5. Play a track, then click Recognize in the companion UI or tap the simulator touchbar.

Keyboard shortcuts in the simulator:
- Up and Down arrows: swipe up and down
- Enter or Space: tap
- Escape: double-tap (back)

## Companion UI (web)

The web page at <http://localhost:5173> shows:

- Current mode (idle, listening, recognizing, fetching-lyrics, playing-synced, and so on)
- Track card with title, artist, album, album art, and the current lyric line
- Recognize: start a capture, same as tapping the glasses
- Pause sync and Resume sync: stop or start the lyric clock without dropping the track
- Reset: back to idle

The companion UI is for debugging. On the glasses, the three gestures above control everything.

## Packaging for Even Hub

```bash
npm run build               # tsc + vite build → dist/
npm run pack:evenhub        # evenhub pack app.json ./dist → out.ehpk
```

Edit `app.json` first:

- `package_id`: reverse-domain, all lowercase, no hyphens (for example `com.you.shazamg2`)
- `author`: your name
- `permissions`: already declares `g2-microphone` and `network` with the hostnames the app fetches

## Architecture

```
src/
├── App.tsx                    companion web UI (status panel + controls)
├── main.tsx                   React mount
├── app.css                    Tailwind + even-toolkit/web theme tokens
├── glass/
│   ├── AppGlasses.tsx         React wrapper — creates controller on mount
│   ├── controller.ts          GlassesController: bridge init, events, render loop
│   ├── events.ts              EvenHubEvent → intent mapper
│   ├── layouts.ts             CreateStartUpPageContainer config + renderers
│   ├── image.ts               URL → 100×100 4-bit greyscale PNG (dithered)
│   ├── png.ts                 Minimal grayscale PNG encoder (uncompressed DEFLATE)
│   └── shared.ts              AppSnapshot / Track / Lyrics types
└── state/
    ├── store.ts               Immutable-replace store (notified subscribers)
    ├── pipeline.ts            runRecognition orchestrator + clock lifecycle
    ├── audio.ts               GlassBridgeSource → Float32 buffer → WAV blob
    ├── audd.ts                AudD multipart POST + response flattening
    ├── lyrics.ts              LRCLIB synced + lyrics.ovh plain fallback
    ├── lrc.ts                 [mm:ss.xx] LRC parser
    └── clock.ts               200 ms setInterval → LRC index via binary search
```

### On-glasses layout (576 x 288, 4-bit greyscale)

The container layout never changes; mode changes only update text, so nothing flickers. Album art is sent asynchronously and never blocks text updates.

```
┌──────────────────────────────────────────────────────┐
│  ┌─────────┐  HEADER (title / artist / album         │
│  │   100   │          or "LISTENING…" etc)           │
│  │  × 100  │                                         │
│  │   ART   │                                         │
│  └─────────┘                                         │
│                                                      │
│  BODY (lyrics with previous / current / next)        │
│                                                      │
│  ▸ current line (highlighted)                        │
│    next line                                         │
│    next next line                                    │
└──────────────────────────────────────────────────────┘
```

### Clock anchor

AudD's `timecode` roughly corresponds to the start of the uploaded clip. The clock anchors to `performance.now()` at the moment the first audio sample was captured (not when AudD responded), so the lyric position matches what you hear right away instead of trailing by about 12 seconds.

## Known limitations

- A WebView cannot read iOS system audio, so the app listens through the glasses mic (or the phone mic through the Even App). To identify music playing in AirPods, play it through speakers or loop it through BlackHole on a Mac.
- The lyric clock is dead reckoning from the recognition anchor, so lyrics keep advancing if you pause the music. Swipe once to enter MANUAL mode, or press Pause sync in the companion UI. Tap or press Resume sync to re-lock when playback resumes.
- LRCLIB is community-sourced, so obscure or new tracks may be missing. The app falls back to plain lyrics from lyrics.ovh, then to metadata only.
- AudD's free and hobby tiers match commercial music. Covers, live versions, and classical recordings may not match; try the studio recording.

## Troubleshooting

### Nothing happens when I tap the glasses

Check that the `useGlasses` bootstrap completed: the companion UI should show `idle` and the glasses should show "SHAZAM G2" with the "Tap to identify" prompt. If the glasses stay blank, page-container creation failed. Look in the browser devtools console (via Safari inspector on iPhone or Chrome DevTools on Android) for `createStartUpPageContainer` errors.

### AudD returns "no match"

The audio was too quiet, the track isn't in AudD's catalog, or the clip caught only background noise. Try a well-known studio track at a higher volume first.

### Lyrics are offset from what I hear

LRCLIB timestamps are community-contributed and are sometimes off by a few seconds. Swipe up/down once to enter MANUAL mode, find the right line, then tap to re-lock sync at that position (restarts the clock from the current manual index).

### The simulator shows no audio activity

Check that macOS has granted Node or the simulator microphone access (System Settings > Privacy & Security > Microphone), and that the `--aid` value matches the device ID from `--list-audio-input-devices`.

### Album art doesn't appear on the glasses

The artwork download is fire-and-forget and can take 2 to 5 seconds after recognition. The image pipeline retries after 3 seconds on failure. Check the devtools console for `[glasses] sendImage` warnings.

## Credits

- PNG encoder + dithering algorithm adapted from [Oliemanq/DisplayPlusMusic](https://github.com/Oliemanq/DisplayPlusMusic) (ISC).
- Built on [`@evenrealities/even_hub_sdk`](https://www.npmjs.com/package/@evenrealities/even_hub_sdk) and [`@evenrealities/pretext`](https://www.npmjs.com/package/@evenrealities/pretext).
