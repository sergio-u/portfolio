# Subtitles G2

SRT subtitle playback for Even Realities G2 glasses, built for watching films in
a theater with subtitles in front of me. The microphone keeps the subtitles in
sync with same-language films. The display shows the current cue and recent
history in a three-row window; long current cues are limited to two rows. The
sibling app [shazam-g2](../shazam-g2/) uses the same glasses SDK.

## Synchronization

- Cloud mode (Soniox) streams a bounded microphone window: 25 seconds for
  "Find my place", 20 seconds for "Re-sync now". Final recognized words are
  matched locally against ordered subtitle words. No LLM call is used.
- Offline mode (experimental) matches speech-band loudness against cue timing.
  It uploads no audio, but music and repeated dialogue rhythms can confuse it.
- "Find my place" searches the whole track. "Re-sync now" starts near the
  running clock; large corrections require another agreeing capture.
- Automatic mode checks every five minutes, backing off to twenty after clean
  readings. A provisional lock gets a check after one minute. Initial searching
  starts only when you ask for it. Inconclusive results leave the clock alone.
- Subtitle speed is explicit and resets when subtitles change. A short audio
  window cannot reliably estimate small framerate differences. Neither mode
  learns playback rate from an isolated correction.

ASR timestamps are anchored to the first captured sample. The app advances that
position through the capture window and all network/recognition delay before
applying a correction. "Residual mic delay" compensates remaining microphone
or Bluetooth buffering after subtracting each delivered PCM block's duration.
Do not enter cloud roundtrip time into that setting.

Manual offset is display-only and survives re-sync. Positive offset shows text
later. "Reset offset" returns it to zero; the separate 500 ms late-display bias
remains. Short pauses hold the previous display for up to 2.5 seconds.

## Cloud setup

This is a personal app. Set `VITE_SONIOX_API_KEY` in Git-ignored `.env.local`
(see `.env.local.example`), and development and production builds include it
automatically. No build flag, token server, or in-app credential entry is
needed. `VITE_SONIOX_MODEL` defaults to `stt-rt-v5`. Anyone with the built app
can extract that key, so do not share builds that embed it; use the token
broker below instead.

Start the development app:

```bash
npm install
npm run dev
```

Restart Vite after changing `.env.local`. Generate the development QR using
Vite's reachable network address:

```bash
npm run qr -- --url http://<your-lan-ip>:5173/
```

Replace that address if your laptop IP changes. Phone and laptop must share
a network. Scan using the Even App development flow. Load matching SRT
subtitles, choose the microphone, grant cloud-audio consent, then select
"Find my place" during sustained dialogue. Consent resets on reload; the
bundled credential remains available. A packaged app only needs access to
Soniox, not to the development laptop.

### Optional token broker

When `VITE_SONIOX_API_KEY` is absent, the app uses broker authentication instead:

1. Copy `.env.asr.local.example` to `.env.asr.local` and set `SONIOX_API_KEY`.
2. Generate a separate client token with `openssl rand -hex 32`; put it in
   `ASR_CLIENT_TOKEN` and enter it in the app's server access token field.
3. Run `npm run dev:asr` alongside Vite. Keep the token URL as `/api/asr-token`;
   Vite proxies it to port 5175. The broker requires Node 20.6+.

The broker binds to localhost, requires authentication, and issues at most six
keys per minute. Its Soniox keys are single-use, expire after 60 seconds, and
limit streaming sessions to 90 seconds. In broker mode, the permanent key stays
server-side. Audio goes directly to Soniox.

For packaged apps using broker mode, host it behind HTTPS and enter its full
`/api/asr-token` URL. Set `ASR_ALLOWED_ORIGINS` to the app's actual origin.
Same-origin HTTP is accepted only on localhost/private IPv4 for trusted-LAN
development. Broker access tokens are session-only.

The client does not store audio or transcripts. Cloud processing still sends
theatre audio to Soniox: review provider retention terms and venue policy.
Revoking consent, changing sync inputs, leaving the page, or cancelling a check
stops the active request. Network failures preserve local playback; offline mode
is an explicit choice, never a silent fallback.

Provider references:
- https://soniox.com/docs/api-reference/stt/websocket-api
- https://soniox.com/docs/guides/temporary-api-keys

## Playback and import

Choose a bundled track, an SRT file, or paste SRT text. The file chooser is
unfiltered because some WebViews hide `.srt` files behind MIME filters. Import
is local; files and pasted text are limited to 5 MB. Subtitles remain in memory
until the app restarts. A single bundled track loads automatically.

| Glasses gesture | Action |
| --- | --- |
| Tap | Find position, or re-sync while playing |
| Scroll up | Subtitles later by 0.5 seconds |
| Scroll down | Subtitles earlier by 0.5 seconds |
| Double-tap | Restart, or exit from the idle page |

Use the phone's "Play/Pause" button for manual playback. The phone preview uses
the same renderer as the glasses. The host may suspend the WebView when the phone
locks; background microphone capture is not guaranteed.

For a packaged app, `npm run build` refreshes `dist`, then `npm run pack:evenhub`
packages it. Packing alone does not build source changes. The normal build embeds
`VITE_SONIOX_API_KEY` when configured; without it, cloud sync requires a reachable
HTTPS broker. Vite's development proxy is not included in packages.
Requires Even App 2.2.6 or later.

## Verification and limits

`tsconfig.check.json` includes production code and all `.check.ts` sources for
non-emitting type checks. The assertion checks cover fuzzy matching, timestamp
extrapolation, cancellation, display history, SRT overlaps and the experimental
offline path. Harness checks use `src/harness/register.mjs` to resolve the app's
extensionless imports under Node.

The matcher requires several consistent cue-start anchors. Nonverbatim
subtitles, speech recognition errors, repeated scenes, or heavy noise can cause
it to refuse a correction. SRT cue boundaries include editorial timing; their
alignment is approximate even with perfect ASR. Thresholds and hardware timing
need real-device evaluation. No guarantee of cinema-level accuracy is implied
by synthetic checks or a successful type check.
