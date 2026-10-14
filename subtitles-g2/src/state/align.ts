import type { Timeline } from './srt'

/**
 * Subtitle-to-audio alignment.
 *
 * A subtitle track is itself a speech/silence signal: dialogue during a cue,
 * nothing between cues. Correlating that pattern against the loudness envelope
 * captured in the room recovers how far the playback clock has drifted, without
 * needing the film, a network service, or any speech recognition.
 *
 * This is an experimental loudness-based approximation, not a speech detector.
 * Similar dialogue rhythms, music and subtitle padding can produce wrong peaks.
 */

export interface Correlation {
  /** Milliseconds the playback clock must move forward to match the room. */
  lagMs: number
  /** Peak normalized correlation, -1..1. */
  score: number
  /** Peak height in standard deviations above the spread of rival positions. */
  z: number
}

/**
 * Reject alignments that are too weak to act on.
 *
 * Rival scores are correlated samples, so z is a heuristic, not a calibrated
 * probability. These conservative gates still require auditorium evaluation.
 */
export const MIN_SCORE = 0.2
export const MIN_Z = 6

/** Below this many rival positions there is no distribution to judge against. */
const MIN_RIVALS = 8

/** Running mean and spread of rival scores, for the confidence test. */
class Rivals {
  private count = 0
  private sum = 0
  private sumSquares = 0
  private maximum = -Infinity

  add(value: number): void {
    this.count++
    this.sum += value
    this.sumSquares += value * value
    this.maximum = Math.max(this.maximum, value)
  }

  /** Standard deviations `value` sits above the accumulated scores. */
  zOf(value: number): number {
    if (this.count < MIN_RIVALS || value <= this.maximum + 0.01) return 0
    const mean = this.sum / this.count
    const variance = Math.max(0, this.sumSquares / this.count - mean * mean)
    const sd = Math.sqrt(variance)
    return sd <= 1e-9 ? 0 : (value - mean) / sd
  }
}

/**
 * Sample a subtitle timeline into a binary speech signal.
 *
 * @param timeline Cue starts and blank end entries, sorted by time.
 * @param startMs Cue time of the first bin.
 * @param binMs Bin width.
 * @param binCount Number of bins to produce.
 */
export function cueSignal(timeline: Timeline, startMs: number, binMs: number, binCount: number): Float32Array {
  const out = new Float32Array(binCount)
  if (timeline.length === 0) return out

  let index = findIndexAt(timeline, startMs)
  for (let i = 0; i < binCount; i++) {
    const t = startMs + i * binMs
    while (index + 1 < timeline.length && timeline[index + 1][0] <= t) index++
    const entry = index >= 0 ? timeline[index] : undefined
    out[i] = entry && entry[1] !== '' ? 1 : 0
  }
  return out
}

/**
 * Find the lag that best aligns `envelope` with `reference`.
 *
 * Both signals are z-scored, so absolute loudness and the speech/silence ratio
 * drop out and only the shape of the pattern matters. A positive lag means the
 * room is ahead of the subtitles.
 *
 * @param envelope Measured loudness bins.
 * @param reference Cue signal covering the search window.
 * @param maxLagBins Largest lag to consider, in bins.
 * @param binMs Bin width, used to convert the winning lag back to milliseconds.
 */
export function correlate(
  envelope: Float32Array,
  reference: Float32Array,
  maxLagBins: number,
  binMs: number,
): Correlation | null {
  const env = zScore(envelope)
  if (!env) return null

  const peaks: { lag: number; score: number }[] = []
  for (let lag = -maxLagBins; lag <= maxLagBins; lag++) {
    const slice = referenceSlice(reference, lag, env.length, maxLagBins)
    if (!slice) continue
    const ref = zScore(slice)
    if (!ref) continue

    let sum = 0
    for (let i = 0; i < env.length; i++) sum += env[i] * ref[i]
    peaks.push({ lag, score: sum / env.length })
  }
  if (peaks.length === 0) return null

  const best = peaks.reduce((a, b) => (b.score > a.score ? b : a))

  // Judge the peak against positions outside its own lobe, so a broad
  // correlation hill is not mistaken for a confident match.
  const lobeBins = Math.max(1, Math.round(1000 / binMs))
  const rivals = new Rivals()
  for (const p of peaks) {
    if (Math.abs(p.lag - best.lag) <= lobeBins) continue
    rivals.add(p.score)
  }

  return { lagMs: best.lag * binMs, score: best.score, z: rivals.zOf(best.score) }
}

/** Whether an alignment is strong and unambiguous enough to act on. */
export function isConfident<T extends { score: number; z: number }>(c: T | null): c is T {
  return c !== null && Number.isFinite(c.score) && Number.isFinite(c.z) && c.score >= MIN_SCORE && c.z >= MIN_Z
}

/** A position found by searching the whole film rather than a window around a guess. */
export interface Located {
  /** Cue time matching the first bin of the envelope. */
  cueTimeMs: number
  /** Playback rate the match was found at; not 1 when the release framerate differs. */
  rate: number
  score: number
  /** Peak height in standard deviations above the spread of rival positions. */
  z: number
}

/** Peaks within this distance of the winner belong to the same lobe, not a rival match. */
const LOBE_MS = 10_000

/**
 * Bins grouped per step of the film-wide pass.
 *
 * Searching at 500ms reduces work but can blur short cues and rate differences.
 * Fine refinement restores position resolution, not reliable fine-rate estimation.
 */
const COARSE_FACTOR = 5

/** Fine bins searched either side of the coarse winner when refining. */
const REFINE_BINS = 2 * COARSE_FACTOR

/**
 * Playback rates to try during acquisition.
 *
 * A subtitle release authored for one framerate played against another runs
 * fast or slow by a fixed ratio. The skew accumulates across the capture window
 * and destroys the correlation, so the rate has to be found at the same time as
 * the position rather than learned afterwards.
 */
export const RATE_CANDIDATES = [
  1, // matching framerate
  25 / 23.976, // PAL subtitles against a 23.976 print
  23.976 / 25, // the reverse
  24 / 23.976, // NTSC pulldown pair
  23.976 / 24,
]

/**
 * Find where in the film an envelope was recorded, searching every position and
 * every candidate rate.
 *
 * This is what lets playback start without the user timing anything: the film
 * may already be twenty minutes in. A two-hour film at 100ms bins is 72k
 * positions per rate.
 *
 * @param envelope Measured loudness bins.
 * @param timeline Cue timeline for the whole film.
 * @param filmDurationMs Total subtitle runtime.
 * @param binMs Bin width.
 * @param rates Playback rates to consider.
 */
export function locate(
  envelope: Float32Array,
  timeline: Timeline,
  filmDurationMs: number,
  binMs: number,
  rates: number[] = RATE_CANDIDATES,
): Located | null {
  if (!timeline.length || !rates.length || !Number.isFinite(binMs) || binMs <= 0 ||
      !Number.isFinite(filmDurationMs) || filmDurationMs <= 0 ||
      rates.some((rate) => !Number.isFinite(rate) || rate < 0.9 || rate > 1.1)) return null
  const coarseBinMs = binMs * COARSE_FACTOR
  const coarseEnv = zScore(downsample(envelope, COARSE_FACTOR))
  if (!coarseEnv) return null

  const n = coarseEnv.length
  const maxRate = Math.max(...rates)
  const total = Math.ceil(filmDurationMs / coarseBinMs) + Math.ceil(n * maxRate) + 1
  const reference = cueSignal(timeline, 0, coarseBinMs, total)

  const scored: Float32Array[] = []
  let best: { start: number; rateIndex: number; score: number } | null = null

  for (let r = 0; r < rates.length; r++) {
    const offsets = rateOffsets(n, rates[r])
    const span = offsets[n - 1] + 1
    if (span >= total) {
      scored.push(new Float32Array(0))
      continue
    }

    const scores = new Float32Array(total - span + 1)
    for (let start = 0; start < scores.length; start++) {
      const score = scoreAt(coarseEnv, reference, offsets, start)
      scores[start] = score
      if (!best || score > best.score) best = { start, rateIndex: r, score }
    }
    scored.push(scores)
  }
  if (!best) return null

  const lobeBins = Math.max(1, Math.round(LOBE_MS / coarseBinMs))
  const rivals = new Rivals()
  for (const scores of scored) {
    for (let start = 0; start < scores.length; start++) {
      // Only rival positions count; the same position found at a neighbouring
      // rate is agreement, not ambiguity.
      if (Math.abs(start - best.start) <= lobeBins) continue
      rivals.add(scores[start])
    }
  }

  const rate = rates[best.rateIndex]
  const coarseStartBin = best.start * COARSE_FACTOR
  const refined = refine(envelope, timeline, filmDurationMs, binMs, rate, coarseStartBin)

  return {
    cueTimeMs: (refined ? refined.start : coarseStartBin) * binMs,
    rate,
    score: refined ? refined.score : best.score,
    z: rivals.zOf(best.score),
  }
}

/** Re-search a narrow window at full resolution, recovering what coarse bins rounded away. */
function refine(
  envelope: Float32Array,
  timeline: Timeline,
  filmDurationMs: number,
  binMs: number,
  rate: number,
  centerBin: number,
): { start: number; score: number } | null {
  const env = zScore(envelope)
  if (!env) return null

  const offsets = rateOffsets(env.length, rate)
  const span = offsets[env.length - 1] + 1
  const total = Math.ceil(filmDurationMs / binMs) + span + 1
  const reference = cueSignal(timeline, 0, binMs, total)

  const from = Math.max(0, centerBin - REFINE_BINS)
  const to = Math.min(total - span, centerBin + REFINE_BINS)
  if (to < from) return null

  let best: { start: number; score: number } | null = null
  for (let start = from; start <= to; start++) {
    const score = scoreAt(env, reference, offsets, start)
    if (!best || score > best.score) best = { start, score }
  }
  return best
}

/** Which reference bin each envelope bin lands on at a given playback rate. */
function rateOffsets(n: number, rate: number): Int32Array {
  const offsets = new Int32Array(n)
  for (let i = 0; i < n; i++) offsets[i] = Math.round(i * rate)
  return offsets
}

/**
 * Normalized correlation of a z-scored envelope against the cue signal at one
 * position.
 *
 * The reference is binary, so E[x^2] equals E[x] and the variance follows from
 * the mean alone; the envelope is zero-mean, so the reference mean drops out.
 */
function scoreAt(env: Float32Array, reference: Float32Array, offsets: Int32Array, start: number): number {
  const n = env.length
  let dot = 0
  let sum = 0
  for (let i = 0; i < n; i++) {
    const v = reference[start + offsets[i]]
    sum += v
    dot += env[i] * v
  }

  const mean = sum / n
  const variance = mean - mean * mean
  if (variance <= 1e-12) return 0
  return dot / (n * Math.sqrt(variance))
}

/** Average `factor` bins into one, for the film-wide acquisition pass. */
function downsample(signal: Float32Array, factor: number): Float32Array {
  const out = new Float32Array(Math.floor(signal.length / factor))
  for (let i = 0; i < out.length; i++) {
    let sum = 0
    for (let j = 0; j < factor; j++) sum += signal[i * factor + j]
    out[i] = sum / factor
  }
  return out
}

/**
 * Fraction of the window covered by dialogue.
 *
 * Windows that are almost all speech or almost all silence carry no timing
 * information, so a capture is worth skipping when the script says one is due.
 */
export function speechRatio(signal: Float32Array): number {
  if (signal.length === 0) return 0
  let sum = 0
  for (const v of signal) sum += v
  return sum / signal.length
}

/**
 * Loudness spread of a captured envelope, in dB.
 *
 * Dialogue alternates between speech and near-silence, giving a wide spread. A
 * continuous music bed, applause, or plain room tone stays at one level, and
 * correlating that against a speech pattern is how a clock gets thrown off.
 * Percentiles rather than min/max, so one door slam cannot fake it, and dB
 * rather than a ratio, because a compressing microphone narrows the spread
 * instead of removing it.
 */
export function envelopeRangeDb(envelope: Float32Array): number {
  if (envelope.length < 10) return 0
  const sorted = Float32Array.from(envelope).sort()
  const quiet = sorted[Math.floor(sorted.length * 0.1)]
  const loud = sorted[Math.floor(sorted.length * 0.9)]
  return loud - quiet
}

/**
 * Whether the script says a window is worth listening to.
 *
 * Checked before opening the microphone: a stretch with no dialogue, or one
 * with unbroken dialogue, cannot pin down timing however good the audio is.
 */
export function referenceIsInformative(
  timeline: Timeline,
  fromMs: number,
  windowMs: number,
  binMs: number,
  minRatio: number,
  maxRatio: number,
): boolean {
  const ratio = speechRatio(cueSignal(timeline, fromMs, binMs, Math.round(windowMs / binMs)))
  return ratio >= minRatio && ratio <= maxRatio
}

function referenceSlice(reference: Float32Array, lag: number, length: number, maxLagBins: number): Float32Array | null {
  const start = maxLagBins + lag
  if (start < 0 || start + length > reference.length) return null
  return reference.subarray(start, start + length)
}

function zScore(signal: Float32Array): Float32Array | null {
  const n = signal.length
  if (n === 0 || signal.some((value) => !Number.isFinite(value))) return null

  let mean = 0
  for (const v of signal) mean += v
  mean /= n

  let variance = 0
  for (const v of signal) variance += (v - mean) * (v - mean)
  variance /= n
  if (variance <= 1e-12) return null // flat signal carries no alignment information

  const sd = Math.sqrt(variance)
  const out = new Float32Array(n)
  for (let i = 0; i < n; i++) out[i] = (signal[i] - mean) / sd
  return out
}

function findIndexAt(timeline: Timeline, timeMs: number): number {
  if (timeline.length === 0 || timeMs < timeline[0][0]) return -1
  let lo = 0
  let hi = timeline.length - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >>> 1
    if (timeline[mid][0] <= timeMs) lo = mid
    else hi = mid - 1
  }
  return lo
}
