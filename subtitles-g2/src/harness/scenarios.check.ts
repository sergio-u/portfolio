/**
 * Scenario harness: a whole screening in milliseconds.
 *
 * Runs the real alignment, transport, and clock modules against a synthetic
 * auditorium on a virtual clock. Each scenario checks the property that matters
 * in a cinema: does the line on the glasses match the line being spoken?
 *
 * Run with: node --experimental-strip-types src/harness/scenarios.check.ts
 */
import './env.ts'

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { clock, flush, installTimers } from './env.ts'
import { FakeRoom, installFakeRoom } from './fakeRoom.ts'
import { findMyPlace, startAutoSync, stopAutoSync, syncNow } from '../state/autosync.ts'
import { startCueClock } from '../state/clock.ts'
import { applyCorrection, cueTimeAt } from '../state/player.ts'
import {
  getAppSnapshot,
  setFilm,
  setMicLatencyMs,
  setOffsetMs,
  setRateFactor,
  setSyncEngine,
} from '../state/store.ts'
import { durationMs, parseSrt, toTimeline, type Cue } from '../state/srt.ts'

/** Correlation is quantised to 100ms bins and small residuals are left alone by design. */
const TOLERANCE_MS = 800

/** A film's worth of irregular dialogue. */
function buildFilm(seed: number, lengthMs: number): Cue[] {
  let state = seed
  const random = () => {
    state = (state * 1103515245 + 12345) % 2147483648
    return state / 2147483648
  }

  const cues: Cue[] = []
  let t = 0
  while (t < lengthMs) {
    const gap = 400 + Math.floor(random() * 6000)
    const len = 800 + Math.floor(random() * 3000)
    cues.push({ startMs: t + gap, endMs: t + gap + len, text: `cue at ${t + gap}` })
    t += gap + len
  }
  return cues
}

const cues = loadCues()
const timeline = toTimeline(cues)
const film = { name: 'Test Film', cues, timeline, durationMs: durationMs(cues) }

/**
 * Real subtitles when one is offered, synthetic dialogue otherwise.
 *
 * Point `SUBTITLES_SRT` at a local file to run the scenarios against real cue
 * rhythm; subtitle files stay out of the repository.
 */
function loadCues(): Cue[] {
  const path = process.env.SUBTITLES_SRT
  if (!path) return buildFilm(20_260_826, 5_400_000)

  const parsed = parseSrt(readFileSync(path, 'utf8'))
  assert.ok(parsed.length > 0, `parsed cues from ${path}`)
  console.log(`  using ${parsed.length} cues from ${path.split('/').pop()}`)
  return parsed
}

/** Reset every piece of persisted or module-level state between scenarios. */
async function reset(): Promise<void> {
  stopAutoSync()
  // Let any capture still in flight finish, otherwise the next scenario's calls
  // are refused as "already listening".
  await clock.advance(60_000)

  setFilm(null)
  setSyncEngine('offline')
  setOffsetMs(0)
  setRateFactor(1)
  setMicLatencyMs(0)
  setFilm(film)
}

/** How far the app's idea of the current line is from what the room is playing. */
function driftMs(room: FakeRoom): number {
  const truth = room.cueTimeAt(clock.now())
  assert.ok(truth !== null, 'room is playing the film')
  return cueTimeAt(clock.now()) - truth
}

async function scenario(name: string, fn: () => Promise<void>): Promise<void> {
  await reset()
  await fn()
  console.log(`  ok  ${name}`)
}

// The SDK replaces window's timers when it loads, so reclaim them now that every
// module has been imported.
installTimers()

console.log('scenarios:')

// --- Display hold --------------------------------------------------------

// A short gap holds the previous line rather than blanking, so dialogue missed
// in the moment can still be read a beat later.
const heldTicks: number[] = []
startCueClock({
  timeline: toTimeline([
    { startMs: 0, endMs: 1000, text: 'first' },
    { startMs: 3000, endMs: 4000, text: 'second' },
  ]),
  positionMs: 1500, // inside the gap after 'first'
  anchorAt: clock.now(),
  holdMs: 2500,
  onTick: (i) => heldTicks.push(i),
})()
assert.deepEqual(heldTicks, [0], 'holds the previous line through a short gap')

const droppedTicks: number[] = []
startCueClock({
  timeline: toTimeline([
    { startMs: 0, endMs: 1000, text: 'first' },
    { startMs: 30_000, endMs: 31_000, text: 'second' },
  ]),
  positionMs: 20_000, // long after the line ended
  anchorAt: clock.now(),
  holdMs: 2500,
  onTick: (i) => droppedTicks.push(i),
})()
assert.deepEqual(droppedTicks, [1], 'clears the display once the gap is long')
console.log('  ok  holds a line through a short gap, clears after a long one')

// --- Arriving late -------------------------------------------------------

await scenario('locks on 25 minutes into the film, with no start cue', async () => {
  const room = new FakeRoom({ timeline, startCueMs: 1_500_000 })
  installFakeRoom(room)

  const result = findMyPlace()
  await clock.advance(60_000)
  await result

  assert.equal(getAppSnapshot().mode, 'playing', 'starts playing after acquisition')
  assert.ok(Math.abs(driftMs(room)) < TOLERANCE_MS, `locked accurately, drift ${driftMs(room).toFixed(0)}ms`)
})

// --- Trailers ------------------------------------------------------------

await scenario('refuses to lock during trailers, then locks when the film starts', async () => {
  const room = new FakeRoom({ timeline, startCueMs: 0, startsAtMs: 600_000 })
  installFakeRoom(room)

  const early = findMyPlace()
  await clock.advance(60_000)
  const earlyResult = await early
  assert.equal(getAppSnapshot().mode, 'searching', 'still searching during trailers')
  assert.match(earlyResult.status, /still listening/i, `reports waiting, got "${earlyResult.status}"`)

  await clock.advance(600_000) // feature begins
  const later = findMyPlace()
  await clock.advance(60_000)
  await later

  assert.equal(getAppSnapshot().mode, 'playing', 'locks once the film is running')
  assert.ok(Math.abs(driftMs(room)) < TOLERANCE_MS, `locked accurately, drift ${driftMs(room).toFixed(0)}ms`)
})

// --- Disturbance ---------------------------------------------------------

await scenario('full acquisition recovers after the film jumps beyond local search', async () => {
  const room = new FakeRoom({ timeline, startCueMs: 900_000, jumps: [{ atMs: 120_000, deltaMs: -30_000 }] })
  installFakeRoom(room)

  const lock = findMyPlace()
  await clock.advance(60_000)
  await lock
  assert.ok(Math.abs(driftMs(room)) < TOLERANCE_MS, 'locked before the jump')

  await clock.advance(70_000) // crosses the jump
  assert.ok(
    Math.abs(driftMs(room)) > 20_000,
    `jump actually knocked it out of sync, drift ${driftMs(room).toFixed(0)}ms`,
  )

  // Offline mode does not infer direction from an ambiguous out-of-range peak.
  const reacquire = findMyPlace()
  await clock.advance(60_000)
  await reacquire

  assert.ok(Math.abs(driftMs(room)) < TOLERANCE_MS, `recovered, drift ${driftMs(room).toFixed(0)}ms`)
})

// --- Framerate mismatch --------------------------------------------------

await scenario('locks onto a mismatched subtitle release and holds it', async () => {
  // 25fps subtitles against a 23.976fps print: ~4% fast, minutes of drift by the end.
  const rate = 25 / 23.976
  const room = new FakeRoom({ timeline, startCueMs: 600_000, rate })
  installFakeRoom(room)
  setRateFactor(rate)

  const lock = findMyPlace()
  await clock.advance(60_000)
  await lock

  assert.equal(getAppSnapshot().mode, 'playing', 'acquires despite the framerate mismatch')
  assert.ok(
    Math.abs(getAppSnapshot().rateFactor - rate) < 0.005,
    `explicit rate retained, got ${getAppSnapshot().rateFactor.toFixed(4)}`,
  )

  // The real test: drift stays small over the next stretch without further help.
  await clock.advance(600_000)
  assert.ok(
    Math.abs(driftMs(room)) < 10_000,
    `drift contained over 10 minutes, ${(driftMs(room) / 1000).toFixed(1)}s`,
  )
})

// --- Music and silence ---------------------------------------------------

await scenario('leaves the clock alone during a music-only passage', async () => {
  const room = new FakeRoom({
    timeline,
    startCueMs: 600_000,
    musicIntervals: [{ fromMs: 90_000, toMs: 600_000 }],
  })
  installFakeRoom(room)

  const lock = findMyPlace()
  await clock.advance(60_000)
  await lock
  assert.ok(Math.abs(driftMs(room)) < TOLERANCE_MS, 'locked on dialogue first')
  const before = driftMs(room)

  // The score takes over: continuous sound carrying no speech pattern.
  await clock.advance(60_000)
  const during = syncNow()
  await clock.advance(40_000)
  const result = await during

  assert.equal(result.appliedMs, null, `no correction drawn from music, got ${result.appliedMs}`)
  assert.ok(
    Math.abs(driftMs(room) - before) < 100,
    `clock untouched through the music, moved ${(driftMs(room) - before).toFixed(0)}ms`,
  )
})

// --- Capture delay -------------------------------------------------------

await scenario('compensates for a known capture delay', async () => {
  const room = new FakeRoom({ timeline, startCueMs: 1_200_000, latencyMs: 400 })
  installFakeRoom(room)
  setMicLatencyMs(400)

  const lock = findMyPlace()
  await clock.advance(60_000)
  await lock

  assert.ok(Math.abs(driftMs(room)) < TOLERANCE_MS, `delay corrected, drift ${driftMs(room).toFixed(0)}ms`)
})

// Acquisition and re-sync have to compensate the capture delay in the same
// direction; a sign disagreement between them shows up as twice the delay.
await scenario('compensates for a known capture delay through re-sync too', async () => {
  const room = new FakeRoom({ timeline, startCueMs: 1_200_000, latencyMs: 800 })
  installFakeRoom(room)
  setMicLatencyMs(800)

  const lock = findMyPlace()
  await clock.advance(60_000)
  await lock

  // Knock the clock out by a known amount, then let one re-sync put it back.
  applyCorrection(4000)
  assert.ok(Math.abs(driftMs(room)) > 3000, 'clock actually knocked out')

  const resync = syncNow()
  await clock.advance(40_000)
  await resync

  assert.ok(Math.abs(driftMs(room)) < TOLERANCE_MS, `re-sync restored it, drift ${driftMs(room).toFixed(0)}ms`)
})

// --- Cinema conditions ---------------------------------------------------

await scenario('locks through a score bed and room reverb', async () => {
  const room = new FakeRoom({ timeline, startCueMs: 2_400_000, bedLevel: 0.3, reverbMs: 400 })
  installFakeRoom(room)

  const lock = findMyPlace()
  await clock.advance(60_000)
  await lock

  assert.equal(getAppSnapshot().mode, 'playing', 'acquires with music under the dialogue')
  // Reverb holds each line up past its end, which biases the match slightly late.
  assert.ok(Math.abs(driftMs(room)) < 2000, `locked, drift ${driftMs(room).toFixed(0)}ms`)
})

await scenario('locks with microphone gain control compressing the room', async () => {
  const room = new FakeRoom({ timeline, startCueMs: 900_000, agc: true })
  installFakeRoom(room)

  const lock = findMyPlace()
  await clock.advance(60_000)
  await lock

  assert.equal(getAppSnapshot().mode, 'playing', 'acquires through gain control')
  assert.ok(Math.abs(driftMs(room)) < TOLERANCE_MS, `locked, drift ${driftMs(room).toFixed(0)}ms`)
})

// --- Loading another film ------------------------------------------------

await scenario('drops a learned framerate ratio when subtitles are replaced', async () => {
  setRateFactor(25 / 23.976)
  setFilm(film)
  assert.equal(getAppSnapshot().rateFactor, 1, 'a ratio from the last film does not carry over')
})

// --- Automatic cadence ---------------------------------------------------

await scenario('widens the checking interval while the clock stays right', async () => {
  const room = new FakeRoom({ timeline, startCueMs: 300_000 })
  installFakeRoom(room)

  const lock = findMyPlace()
  await clock.advance(60_000)
  await lock

  startAutoSync()
  const first = getAppSnapshot().syncCadenceMs
  assert.ok(first !== null, 'reports a cadence once running')

  // Several clean cycles: nothing needs correcting, so checks should get rarer.
  await clock.advance(30 * 60_000)
  await flush()

  const later = getAppSnapshot().syncCadenceMs
  assert.ok(later !== null && later > (first as number), `cadence widened from ${first}ms to ${later}ms`)
  assert.ok(Math.abs(driftMs(room)) < TOLERANCE_MS, 'still in sync after backing off')

  stopAutoSync()
})

console.log('scenarios.check.ts: all scenarios passed')
