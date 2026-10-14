/** Full ASR flow with fake microphone, broker and WebSocket; never contacts Soniox. */
import './env.ts'
import assert from 'node:assert/strict'
import { clock, installTimers } from './env.ts'
import { setAudioSourceFactory } from '../state/capture.ts'
import type { AudioListener } from '../state/audioSources.ts'
import { findMyPlace, stopAutoSync, syncNow } from '../state/autosync.ts'
import { cueTimeAt, lockTo, nudgeOffset, play, seekTo, stop } from '../state/player.ts'
import { getAppSnapshot, getSyncRevision, setAsrAccessToken, setAsrConsent, setFilm,
  setOffsetMs, setSyncEngine } from '../state/store.ts'
import { durationMs, toTimeline } from '../state/srt.ts'
import { tokensToWords, transcribeLive } from '../state/asr.ts'

installTimers()
const base = 600_000
const cues = [
  { startMs: base, endMs: base + 3500, text: 'Captain Morgan found the missing compass yesterday' },
  { startMs: base + 5000, endMs: base + 8500, text: 'Silver lanterns mark the northern harbor entrance' },
  { startMs: base + 10_000, endMs: base + 13_500, text: 'Tomorrow morning bring your maps to headquarters' },
  { startMs: base + 15_000, endMs: base + 18_500, text: 'Nobody expected pirates beyond the frozen mountain' },
]
const film = { name: 'Fake ASR film', cues, timeline: toTimeline(cues), durationMs: durationMs(cues) }
const globals = globalThis as unknown as Record<string, unknown>
const originalFetch = globals.fetch
const originalSocket = globals.WebSocket
;(window as unknown as Record<string, unknown>).location = { href: 'http://localhost:5173/', origin: 'http://localhost:5173' }
let uploads = 0
let stopped = 0
let sockets = 0
let providerDelay = 9000
let brokerRequests = 0
let expectedKey = 'fake-temporary-key'

class FakeSocket {
  static OPEN = 1
  readyState = 0
  bufferedAmount = 0
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  private audioMs = 0
  private responseTimer: number | undefined
  constructor() {
    sockets++
    clock.setTimeout(() => { if (this.readyState === 0) { this.readyState = 1; this.onopen?.() } }, 0)
  }
  send(data: string | ArrayBuffer) {
    if (data instanceof ArrayBuffer) { this.audioMs += data.byteLength / 32; uploads++; return }
    if (data) { assert.equal(JSON.parse(data).api_key, expectedKey); return }
    this.responseTimer = clock.setTimeout(() => {
      const tokens = cues.flatMap((cue) => cue.text.split(' ').map((text, i) => ({
        text: ` ${text}`, start_ms: cue.startMs - base + i * 400,
        end_ms: cue.startMs - base + i * 400 + 250, confidence: 0.95, is_final: true,
      })))
      this.onmessage?.({ data: JSON.stringify({ tokens, final_audio_proc_ms: this.audioMs, finished: true }) })
    }, providerDelay)
  }
  close() {
    if (this.readyState === 3) return
    this.readyState = 3
    if (this.responseTimer !== undefined) clock.clearTimeout(this.responseTimer)
    this.onclose?.()
  }
}

globals.WebSocket = FakeSocket
globals.fetch = async () => {
  brokerRequests++
  return new Response(JSON.stringify({ api_key: 'fake-temporary-key', model: 'stt-rt-v5' }))
}
setAudioSourceFactory(async () => {
  let callback: AudioListener = () => {}
  let timer: number | undefined
  const stopCapture = () => { if (timer !== undefined) clock.clearInterval(timer); timer = undefined }
  return {
    async start() { timer = clock.setInterval(() => callback(new Float32Array(1600), 16_000), 100) },
    stop: stopCapture,
    onAudioData(listener) { callback = listener; return () => { callback = () => {} } },
    dispose() { stopCapture(); stopped++ },
  }
})

try {
  setFilm(film)
  setSyncEngine('asr')
  const denied = await findMyPlace()
  assert.match(denied.status, /consent/)
  assert.equal(sockets, 0, 'no upload or provider connection without consent')
  setAsrConsent(true)
  setAsrAccessToken('fake-server-access-token')
  const started = clock.now()
  const acquire = findMyPlace()
  await clock.advance(40_000)
  await acquire
  assert.equal(getAppSnapshot().mode, 'playing')
  assert.ok(Math.abs(cueTimeAt(clock.now()) - (base + clock.now() - started)) < 1,
    'capture plus nine seconds of provider delay advance the clock exactly once')
  assert.ok(uploads > 0)
  assert.ok(stopped > 0, 'microphone closes before the completed result is used')
  assert.equal(brokerRequests, 1, 'broker credentials are used when no direct key is supplied')

  expectedKey = 'fake-internal-dev-key'
  const direct = transcribeLive(20_000, { apiKey: expectedKey, tokenUrl: '', accessToken: '' })
  await clock.advance(35_000)
  assert.ok((await direct).words.length > 0, 'direct credentials use the same timestamped stream')
  assert.equal(brokerRequests, 1, 'direct credentials bypass the broker even without its URL or token')
  expectedKey = 'fake-temporary-key'

  const position = cueTimeAt(clock.now())
  nudgeOffset(1000)
  assert.equal(cueTimeAt(clock.now()), position, 'manual display delay is excluded from alignment')
  const revision = getSyncRevision()
  nudgeOffset(500); nudgeOffset(-500)
  assert.ok(getSyncRevision() > revision, 'change-and-revert still invalidates an in-flight measurement')

  const pending = findMyPlace()
  await clock.advance(1000)
  setFilm(null)
  const bytesAtCancel = uploads
  await clock.advance(40_000)
  await pending
  assert.equal(getAppSnapshot().film, null)
  assert.equal(getAppSnapshot().mode, 'empty', 'late results cannot restore a removed film')
  assert.equal(uploads, bytesAtCancel, 'film replacement stops cloud audio')

  setFilm(film)
  setOffsetMs(0)
  lockTo(base + 2000, clock.now())
  assert.notEqual(getAppSnapshot().currentIndex, -1)
  seekTo(0)
  assert.equal(getAppSnapshot().currentIndex, -1, 'seeking before first cue immediately clears the display')
  setFilm(null)
  await clock.advance(10_000)
  assert.equal(getAppSnapshot().currentIndex, -1, 'old timers cannot write indices after film replacement')

  setFilm(film)
  play()
  providerDelay = 90_000
  const timeout = syncNow()
  await clock.advance(70_000)
  const failure = await timeout
  assert.match(failure.status, /timed out/)
  assert.equal(getAppSnapshot().mode, 'playing', 'provider failure does not stop local playback')
  assert.equal(getAppSnapshot().syncBusy, false)

  assert.deepEqual(tokensToWords([
    { text: 'Good', start_ms: 0, end_ms: 100, confidence: 1 },
    { text: 'bye', start_ms: 100, end_ms: 200, confidence: 0.9 },
    { text: ' friend', start_ms: 300, end_ms: 500, confidence: 1 },
  ]).map((word) => word.text), ['Goodbye', 'friend'])
} finally {
  stopAutoSync()
  stop()
  setAudioSourceFactory(null)
  globals.fetch = originalFetch
  globals.WebSocket = originalSocket
}
console.log('asr.check.ts: all assertions passed')
