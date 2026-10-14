import { captureAudio, type CaptureOptions } from './capture'
export { createAudioSource, setAudioSourceFactory, type CaptureOptions } from './capture'

/** Offline envelope resolution in milliseconds. */
export const ENVELOPE_BIN_MS = 100

/** Offline speech-band loudness bins and their sample-clock origin. */
export interface Envelope {
  bins: Float32Array
  binMs: number
  startedAt: number
}

/** Capture a bounded speech-band dB envelope without retaining raw audio. */
export async function captureEnvelope(durationMs: number, opts: CaptureOptions = {}): Promise<Envelope> {
  const bins: number[] = []
  let count = 0
  let sumSquares = 0
  let filter: ((sample: number) => number) | undefined
  const timing = await captureAudio(durationMs, (pcm, rate) => {
    filter ??= createBandPass(rate)
    const samplesPerBin = Math.round(rate * ENVELOPE_BIN_MS / 1000)
    for (const sample of pcm) {
      const voice = filter(sample)
      sumSquares += voice * voice
      if (++count >= samplesPerBin) {
        bins.push(20 * Math.log10(Math.max(Math.sqrt(sumSquares / count), 1e-6)))
        sumSquares = 0
        count = 0
      }
    }
  }, opts)
  return { bins: Float32Array.from(bins), binMs: ENVELOPE_BIN_MS, startedAt: timing.startedAt }
}

/** First-order filters reduce out-of-band energy; they do not isolate dialogue from music. */
function createBandPass(sampleRate: number): (sample: number) => number {
  const dt = 1 / sampleRate
  const highRc = 1 / (2 * Math.PI * 300)
  const highAlpha = highRc / (highRc + dt)
  const lowRc = 1 / (2 * Math.PI * 3400)
  const lowAlpha = dt / (lowRc + dt)
  let previousIn = 0
  let previousHigh = 0
  let low = 0
  return (sample) => {
    const high = highAlpha * (previousHigh + sample - previousIn)
    previousIn = sample
    previousHigh = high
    low += lowAlpha * (high - low)
    return low
  }
}
