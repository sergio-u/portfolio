import { captureEnvelope } from './audio'
import { correlate, cueSignal, envelopeRangeDb, isConfident, locate, referenceIsInformative } from './align'
import type { AppSnapshot } from '../glass/shared'
import { cueTimeAt } from './player'

/** Experimental offline estimate at the first captured sample; null leaves the clock unchanged. */
export async function measureOffline(snap: AppSnapshot, acquire: boolean, signal: AbortSignal): Promise<{
  cueTimeMs: number; startedAt: number; rate: number
} | null> {
  if (!snap.film) return null
  const durationMs = acquire ? 45_000 : 20_000
  if (!acquire && !referenceIsInformative(snap.film.timeline, cueTimeAt(performance.now()),
    durationMs * snap.rateFactor, 100 * snap.rateFactor, 0.15, 0.85)) return null
  const envelope = await captureEnvelope(durationMs, {
    preferredSource: snap.audioSource, sidecarUrl: snap.sidecarUrl, signal,
  })
  signal.throwIfAborted()
  if (envelopeRangeDb(envelope.bins) < 6) return null
  if (acquire) {
    // A short window cannot resolve small FPS differences reliably. Honor the
    // explicit rate setting instead of treating a quantization tie as a measurement.
    const found = locate(envelope.bins, snap.film.timeline, snap.film.durationMs, envelope.binMs, [snap.rateFactor])
    return isConfident(found) ? { cueTimeMs: found.cueTimeMs, startedAt: envelope.startedAt, rate: found.rate } : null
  }
  const expected = cueTimeAt(envelope.startedAt)
  const stepMs = envelope.binMs * snap.rateFactor
  const maxLagBins = Math.round(20_000 / stepMs)
  const reference = cueSignal(snap.film.timeline, expected - maxLagBins * stepMs,
    stepMs, envelope.bins.length + 2 * maxLagBins)
  const match = correlate(envelope.bins, reference, maxLagBins, stepMs)
  if (!isConfident(match) || Math.abs(match.lagMs) >= 18_000) return null
  return { cueTimeMs: expected + match.lagMs, startedAt: envelope.startedAt, rate: snap.rateFactor }
}
