import type { Cue } from './srt'

/** A recognized word, timed relative to the first sample sent to ASR. */
export interface TranscriptWord {
  text: string
  startMs: number
  endMs: number
  confidence: number
}

/** A passage match anchored to audio time, not provider response time. */
export interface TranscriptMatch {
  /** Subtitle time at audio time zero, using the supplied playback rate. */
  cueTimeMs: number
  matchedWords: number
  matchedCues: number
  /** Median disagreement between cue-boundary anchors, in subtitle milliseconds. */
  uncertaintyMs: number
}

type Word = { text: string; cue: number; first: boolean; weight: number }
const segmenter = typeof Intl.Segmenter === 'function' ? new Intl.Segmenter(undefined, { granularity: 'word' }) : null

/** Split words with source-string indices, including scripts that do not use spaces. */
export function segmentWords(text: string): { text: string; index: number }[] {
  if (segmenter) return [...segmenter.segment(text)].filter((part) => part.isWordLike)
    .map((part) => ({ text: part.segment, index: part.index }))
  return [...text.matchAll(/[\p{L}\p{N}]+(?:'[\p{L}]+)?/gu)].map((part) => ({ text: part[0], index: part.index! }))
}

/** Normalize case, punctuation and common English contractions for matching only. */
function words(text: string): string[] {
  const normalized = text.normalize('NFKC').toLowerCase()
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/\bcan't\b/g, 'can not').replace(/\bwon't\b/g, 'will not')
    .replace(/n't\b/g, ' not').replace(/'ve\b/g, ' have')
    .replace(/'re\b/g, ' are').replace(/'ll\b/g, ' will')
    .replace(/\bi'm\b/g, 'i am')
  return segmentWords(normalized).map((part) => part.text)
}

/**
 * Match noisy speech against consecutive subtitle words using local sequence alignment.
 *
 * Requires several cue starts with consistent timing. SRT has no word times:
 * interior-word interpolation is deliberately not used to estimate the clock.
 * @param cues Subtitle cues sorted by start time.
 * @param transcript Final recognized words with audio-relative timestamps.
 * @param rate Fixed subtitle milliseconds per audio millisecond.
 * @param near Optional expected cue time at audio zero; limits re-sync to +/-30 seconds.
 * @returns A supported, unambiguous position, or null when evidence is insufficient.
 */
export function matchTranscript(
  cues: Cue[], transcript: TranscriptWord[], rate = 1, near?: number,
): TranscriptMatch | null {
  if (!Number.isFinite(rate) || rate < 0.9 || rate > 1.1) return null
  const heard = transcript.flatMap((word) => {
    if (!Number.isFinite(word.startMs) || !Number.isFinite(word.endMs) ||
        word.startMs < 0 || word.endMs < word.startMs ||
        !Number.isFinite(word.confidence) || word.confidence < 0.35) return []
    return words(word.text).map((text) => ({ ...word, text }))
  })
  if (heard.length < 8 || heard.length > 400) return null
  if (heard.some((w, i) => i > 0 && w.startMs < heard[i - 1].startMs)) return null

  const counts = new Map<string, number>()
  const reference: Word[] = []
  const from = near === undefined ? -Infinity : near - 30_000
  const to = near === undefined ? Infinity : near + heard[heard.length - 1].endMs * rate + 30_000
  cues.forEach((cue, cueIndex) => {
    if (cue.startMs < from || cue.startMs > to) return
    // Non-speech labels should not become lexical anchors.
    const tokens = words(cue.text.replace(/\[[^\]]*\]|\([^)]*\)/g, ' '))
    tokens.forEach((text, i) => {
      reference.push({ text, cue: cueIndex, first: i === 0, weight: 1 })
      counts.set(text, (counts.get(text) ?? 0) + 1)
    })
  })
  if (!reference.length || reference.length > 60_000) return null
  for (const word of reference) word.weight = 1 + Math.min(2, Math.log(1 + 10 / counts.get(word.text)!))

  // Two score rows plus one byte per traceback cell keep film-wide search bounded.
  const width = reference.length + 1
  const trace = new Uint8Array((heard.length + 1) * width)
  let previous = new Float32Array(width)
  const peaks = new Float32Array(width)
  const peakRows = new Uint16Array(width)
  for (let i = 1; i <= heard.length; i++) {
    const row = new Float32Array(width)
    for (let j = 1; j < width; j++) {
      const equal = heard[i - 1].text === reference[j - 1].text
      const diagonal = previous[j - 1] + (equal ? reference[j - 1].weight : -1.5)
      const dropHeard = previous[j] - 1.2
      const dropReference = row[j - 1] - 1.2
      const score = Math.max(0, diagonal, dropHeard, dropReference)
      row[j] = score
      trace[i * width + j] = score === 0 ? 0 : score === diagonal ? 1 : score === dropHeard ? 2 : 3
      if (score > peaks[j]) { peaks[j] = score; peakRows[j] = i }
    }
    previous = row
  }
  let winner = 1
  for (let j = 2; j < width; j++) if (peaks[j] > peaks[winner]) winner = j

  const pairs: { heard: number; reference: number }[] = []
  let i = peakRows[winner]
  let j = winner
  while (i > 0 && j > 0) {
    const step = trace[i * width + j]
    if (!step) break
    if (step === 1) {
      if (heard[i - 1].text === reference[j - 1].text) pairs.push({ heard: i - 1, reference: j - 1 })
      i--; j--
    } else if (step === 2) i--
    else j--
  }
  pairs.reverse()
  if (pairs.length < 8 || pairs.length / heard.length < 0.45) return null
  const start = reference[pairs[0].reference].cue
  const end = reference[pairs[pairs.length - 1].reference].cue
  let rival = 0
  for (let k = 1; k < width; k++) {
    const cue = reference[k - 1].cue
    if (cue < start || cue > end + 1) rival = Math.max(rival, peaks[k])
  }
  if (peaks[winner] < 16 || peaks[winner] < rival * 1.2 + 2) return null

  const anchors: { offset: number; at: number; cue: number }[] = []
  for (let k = 0; k + 1 < pairs.length; k++) {
    const pair = pairs[k]
    const next = pairs[k + 1]
    const word = reference[pair.reference]
    // Two consecutive recognized words must support each cue-start anchor.
    if (!word.first || next.reference !== pair.reference + 1 || next.heard !== pair.heard + 1) continue
    anchors.push({ offset: cues[word.cue].startMs - heard[pair.heard].startMs * rate,
      at: heard[pair.heard].startMs, cue: word.cue })
  }
  if (anchors.length < 3) return null
  const center = median(anchors.map((a) => a.offset))
  const agreed = anchors.filter((a) => Math.abs(a.offset - center) <= 1500)
  if (agreed.length < 3 || agreed.length < anchors.length * 0.75 ||
      agreed[agreed.length - 1].at - agreed[0].at < 6000) return null
  const cueTimeMs = median(agreed.map((a) => a.offset))
  return { cueTimeMs, matchedWords: pairs.length, matchedCues: agreed.length,
    uncertaintyMs: median(agreed.map((a) => Math.abs(a.offset - cueTimeMs))) }
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2
}

/** Advance an audio-anchored match through capture, network and processing time. */
export function matchedPositionAt(
  cueTimeMs: number, capturedAt: number, now: number, rate: number, micLatencyMs: number,
): number {
  return cueTimeMs + (now - capturedAt + micLatencyMs) * rate
}
