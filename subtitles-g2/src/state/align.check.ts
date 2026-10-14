/**
 * Self-check for cue-signal sampling and envelope correlation.
 *
 * Run with: node --experimental-strip-types src/state/align.check.ts
 */
import assert from 'node:assert/strict'
import { correlate, cueSignal, isConfident, locate, speechRatio } from './align.ts'
import { toTimeline } from './srt.ts'

const BIN_MS = 100

/** Deterministic noise, so a failure is always reproducible. */
function noise(seed: number): () => number {
  let state = seed
  return () => {
    state = (state * 1103515245 + 12345) % 2147483648
    return state / 2147483648 - 0.5
  }
}

// --- cueSignal ------------------------------------------------------------

const timeline = toTimeline([
  { startMs: 1000, endMs: 3000, text: 'one' },
  { startMs: 5000, endMs: 6000, text: 'two' },
])

const signal = cueSignal(timeline, 0, 1000, 8)
assert.deepEqual(Array.from(signal), [0, 1, 1, 0, 0, 1, 0, 0], 'marks dialogue bins only')
assert.equal(speechRatio(signal), 3 / 8)
assert.equal(speechRatio(new Float32Array(0)), 0)

// --- correlate ------------------------------------------------------------

// A pseudo-random speech/silence pattern: irregular, like real dialogue.
const rand = noise(42)
const pattern = new Float32Array(600)
for (let i = 0; i < pattern.length; ) {
  const run = 3 + Math.floor((rand() + 0.5) * 25)
  const value = i % 2 === 0 ? 1 : 0
  for (let j = 0; j < run && i < pattern.length; j++, i++) pattern[i] = value
}

const MAX_LAG_BINS = 100
const SHIFT_BINS = 37

// The measured envelope is the pattern at a shifted position, plus room noise.
const envNoise = noise(7)
const envelope = new Float32Array(200)
for (let i = 0; i < envelope.length; i++) {
  envelope[i] = pattern[MAX_LAG_BINS + SHIFT_BINS + i] * 0.8 + 0.1 + envNoise() * 0.15
}

const match = correlate(envelope, pattern, MAX_LAG_BINS, BIN_MS)
assert.ok(match, 'finds a match')
assert.equal(match.lagMs, SHIFT_BINS * BIN_MS, 'recovers the shift, positive when the room runs ahead')
assert.ok(isConfident(match), `confident match, got score=${match.score.toFixed(2)} z=${match.z.toFixed(1)}`)

// A flat envelope carries no timing information at all.
assert.equal(correlate(new Float32Array(200).fill(0.5), pattern, MAX_LAG_BINS, BIN_MS), null, 'flat envelope rejected')

// A perfectly periodic pattern matches equally well at many lags, so the result
// must not be treated as confident — this is the music-only failure mode.
const periodic = new Float32Array(600)
for (let i = 0; i < periodic.length; i++) periodic[i] = Math.floor(i / 10) % 2
const periodicWindow = periodic.subarray(MAX_LAG_BINS, MAX_LAG_BINS + 200)
const ambiguous = correlate(periodicWindow, periodic, MAX_LAG_BINS, BIN_MS)
assert.ok(ambiguous, 'periodic input still correlates')
assert.ok(!isConfident(ambiguous), `ambiguous match rejected, got z=${ambiguous.z.toFixed(1)}`)

// --- locate ---------------------------------------------------------------

// A film-length timeline with irregular dialogue, and a capture taken from deep
// inside it: acquisition must find that position without being told where to look.
const filmRand = noise(99)
const cues: { startMs: number; endMs: number; text: string }[] = []
let t = 0
while (t < 3_600_000) {
  const gap = 500 + Math.floor((filmRand() + 0.5) * 6000)
  const len = 800 + Math.floor((filmRand() + 0.5) * 3000)
  cues.push({ startMs: t + gap, endMs: t + gap + len, text: 'line' })
  t += gap + len
}
const filmTimeline = toTimeline(cues)
const FILM_MS = cues[cues.length - 1].endMs

// Acquisition is gated on how far the winning position stands above the scores
// of unrelated positions in the same capture, rather than on a fixed
// correlation value that no auditorium would reach.
/** 45s at 100ms bins. */
const ACQUIRE_BINS = 450

const TRUE_POSITION_MS = 1_500_000 // 25 minutes in
const capture = cueSignal(filmTimeline, TRUE_POSITION_MS, BIN_MS, ACQUIRE_BINS)
const captureNoise = noise(11)
const measured = new Float32Array(capture.length)
for (let i = 0; i < capture.length; i++) measured[i] = capture[i] * 0.8 + 0.1 + captureNoise() * 0.15

const found = locate(measured, filmTimeline, FILM_MS, BIN_MS)
assert.ok(found, 'locates the capture')
assert.equal(found.cueTimeMs, TRUE_POSITION_MS, 'recovers the absolute position')
assert.equal(found.rate, 1, 'reports a matching playback rate')
assert.ok(isConfident(found), `passes the confidence gate, got z=${found.z.toFixed(1)}`)

// A release authored for a different framerate: the skew accumulates across the
// window and defeats a fixed-rate search, so the rate is found alongside the
// position.
const MISMATCH = 25 / 23.976
const skewed = new Float32Array(ACQUIRE_BINS)
const skewNoise = noise(13)
for (let i = 0; i < skewed.length; i++) {
  const cue = TRUE_POSITION_MS + i * BIN_MS * MISMATCH
  skewed[i] = cueSignal(filmTimeline, cue, BIN_MS, 1)[0] * 0.8 + 0.1 + skewNoise() * 0.15
}
const skewFound = locate(skewed, filmTimeline, FILM_MS, BIN_MS)
assert.ok(skewFound, 'locates a framerate-mismatched capture')
assert.ok(
  Math.abs(skewFound.rate - MISMATCH) < 0.005,
  `reports the mismatched rate, got ${skewFound.rate.toFixed(4)}`,
)
assert.ok(
  Math.abs(skewFound.cueTimeMs - TRUE_POSITION_MS) <= 1000,
  `still finds the position, off by ${skewFound.cueTimeMs - TRUE_POSITION_MS}ms`,
)
assert.ok(isConfident(skewFound), `passes the confidence gate, got z=${skewFound.z.toFixed(1)}`)

// Audio unrelated to the film — trailers — must not produce a confident lock.
// Several seeds, because a single one proves nothing about a rejection rule.
for (const seed of [5, 17, 23, 31, 44]) {
  const unrelated = noise(seed)
  const trailer = new Float32Array(ACQUIRE_BINS)
  // Unrelated speech has its own rhythm, so rejection must come from the
  // correlation rather than from the audio looking featureless.
  let run = 0
  let loud = false
  for (let i = 0; i < trailer.length; i++) {
    if (run <= 0) {
      run = 3 + Math.floor((unrelated() + 0.5) * 25)
      loud = !loud
    }
    run--
    trailer[i] = (loud ? 0.9 : 0.1) + unrelated() * 0.15
  }
  const spurious = locate(trailer, filmTimeline, FILM_MS, BIN_MS)
  assert.ok(
    !isConfident(spurious),
    `seed ${seed}: unrelated audio rejected, got score=${spurious?.score.toFixed(2)} z=${spurious?.z.toFixed(1)}`,
  )
}

assert.equal(isConfident({ score: 1, z: Infinity }), false, 'non-finite confidence fails closed')
const oneLag = correlate(envelope, pattern.subarray(MAX_LAG_BINS + SHIFT_BINS, MAX_LAG_BINS + SHIFT_BINS + envelope.length), 0, BIN_MS)
assert.ok(oneLag)
assert.equal(isConfident(oneLag), false, 'no rival positions means insufficient evidence')
assert.equal(locate(measured, filmTimeline, FILM_MS, BIN_MS, []), null)

console.log('align.check.ts: all assertions passed')
