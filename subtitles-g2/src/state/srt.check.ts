/**
 * Self-check for the SRT parser and timeline flattening.
 *
 * Run with: node --experimental-strip-types src/state/srt.check.ts
 */
import assert from 'node:assert/strict'
import { durationMs, parseSrt, toTimeline } from './srt.ts'

const SAMPLE = [
  '1',
  '00:00:12,000 --> 00:00:14,500',
  'First line',
  '',
  '2',
  '00:00:14,500 --> 00:00:16,000',
  '<i>Second</i> line',
  'wrapped across two rows',
  '',
  '3',
  '00:01:00.250 --> 00:01:02,000',
  'Third line',
  '',
].join('\r\n')

const cues = parseSrt('\uFEFF' + SAMPLE)

assert.equal(cues.length, 3, 'parses every well-formed block')
assert.equal(cues[0].startMs, 12_000)
assert.equal(cues[0].endMs, 14_500)
assert.equal(cues[1].text, 'Second line wrapped across two rows', 'strips tags and joins wrapped rows')
assert.equal(cues[2].startMs, 60_250, 'accepts a dot as the millisecond separator')
assert.equal(durationMs(cues), 62_000)

const timeline = toTimeline(cues)

// Cue 1 runs straight into cue 2, so no blank is inserted between them.
assert.deepEqual(timeline[0], [12_000, 'First line'])
assert.deepEqual(timeline[1], [14_500, 'Second line wrapped across two rows'])
// Cue 2 ends well before cue 3 starts, so the display is cleared in the gap.
assert.deepEqual(timeline[2], [16_000, ''])
assert.deepEqual(timeline[3], [60_250, 'Third line'])
assert.deepEqual(timeline[4], [62_000, ''])

// Timeline timestamps must stay sorted or the clock's binary search breaks.
const times = timeline.map(([t]) => t)
assert.deepEqual(times, [...times].sort((a, b) => a - b), 'timeline is sorted by time')

assert.deepEqual(parseSrt('not a subtitle file'), [], 'garbage input yields no cues')
assert.deepEqual(parseSrt(''), [], 'empty input yields no cues')

const nested = [
  { startMs: 0, endMs: 10_000, text: 'outer' },
  { startMs: 2000, endMs: 3000, text: 'inner' },
]
assert.deepEqual(toTimeline(nested), [[0, 'outer'], [2000, 'outer inner'], [3000, 'outer'], [10_000, '']])
assert.equal(durationMs(nested), 10_000, 'nested short cue does not shorten runtime')
assert.deepEqual(parseSrt('1\n00:70:00,000 --> 00:71:00,000\ninvalid'), [], 'invalid minutes rejected')
assert.deepEqual(parseSrt('1\n00:00:02,000 --> 00:00:01,000\nbackwards'), [], 'reversed intervals rejected')

console.log('srt.check.ts: all assertions passed')
