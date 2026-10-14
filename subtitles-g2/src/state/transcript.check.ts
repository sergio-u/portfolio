/** Pure matcher and timestamp regression checks; no microphone, network or provider credentials. */
import assert from 'node:assert/strict'
import { matchTranscript, matchedPositionAt, type TranscriptWord } from './transcript.ts'
import type { Cue } from './srt.ts'

const base = 600_000
const cues: Cue[] = [
  { startMs: base, endMs: base + 3500, text: 'Captain Morgan found the missing compass yesterday' },
  { startMs: base + 5000, endMs: base + 8500, text: 'Silver lanterns mark the northern harbor entrance' },
  { startMs: base + 10_000, endMs: base + 13_500, text: 'Tomorrow morning bring your maps to headquarters' },
  { startMs: base + 15_000, endMs: base + 18_500, text: 'Nobody expected pirates beyond the frozen mountain' },
]
function transcript(rate = 1): TranscriptWord[] {
  return cues.flatMap((cue) => cue.text.split(' ').map((text, i) => ({
    text, startMs: (cue.startMs - base + i * 400) / rate,
    endMs: (cue.startMs - base + i * 400 + 250) / rate, confidence: 0.9,
  })))
}
for (const rate of [1, 25 / 24]) {
  const clean = matchTranscript(cues, transcript(rate), rate)
  assert.ok(clean, 'several ordered cue starts locate the passage')
  assert.equal(clean.cueTimeMs, base)
  assert.equal(clean.matchedCues, 4)
  const noisy = transcript(rate).filter((_, i) => i % 7 !== 5)
    .map((word, i) => i === 3 ? { ...word, text: 'mistaken' } : word)
  assert.ok(matchTranscript(cues, noisy, rate), 'omissions and a substitution need no LLM')
}
const duplicate = [...cues, ...cues.map((cue) => ({ ...cue, startMs: cue.startMs + 100_000, endMs: cue.endMs + 100_000 }))]
assert.equal(matchTranscript(duplicate, transcript()), null, 'identical rival passage prevents a global lock')
assert.ok(matchTranscript(duplicate, transcript(), 1, base), 'local re-sync can use the existing position')
assert.equal(matchTranscript(cues, transcript().slice(0, 7)), null, 'one cue cannot establish sync')
assert.equal(matchTranscript(cues, transcript().map((word) => ({ ...word, text: 'unrelated advertisement' }))), null)
assert.equal(matchTranscript(cues, transcript().map((word) => ({ ...word, confidence: 0.1 }))), null)
assert.equal(matchTranscript(cues, transcript().map((word) => ({ ...word, startMs: NaN }))), null)

// Subtitle word pacing is intentionally nonuniform. Only supported cue starts anchor time.
const irregular = transcript().map((word, i) => i % 7 > 1 ? { ...word, startMs: word.startMs + 250, endMs: word.endMs + 250 } : word)
assert.equal(matchTranscript(cues, irregular)?.cueTimeMs, base)
const capturedAt = 12_345
for (const rate of [1, 25 / 24]) {
  const arrived = capturedAt + 25_000 + 8000 // capture plus network and processing
  assert.equal(matchedPositionAt(base, capturedAt, arrived, rate, 300), base + 33_300 * rate)
  const slow = matchedPositionAt(base, capturedAt, arrived + 10_000, rate, 300)
  assert.ok(Math.abs(slow - matchedPositionAt(base, capturedAt, arrived, rate, 300) - 10_000 * rate) < 1e-6)
}
console.log('transcript.check.ts: all assertions passed')
