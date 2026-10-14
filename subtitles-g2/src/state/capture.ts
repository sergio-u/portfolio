import { AudioInputSource } from '@evenrealities/even_hub_sdk'
import { GlassAudioSource, MicrophoneAudioSource, WebSocketAudioSource, type AudioSource as Input } from './audioSources'
import { isGlassReady, waitForGlassReady } from '../glass/bridgeState'
import type { AudioSource } from '../glass/shared'

/** Microphone selection and cancellation for one bounded capture. */
export interface CaptureOptions {
  preferredSource?: AudioSource
  sidecarUrl?: string
  bridgeWaitMs?: number
  signal?: AbortSignal
}

/** Sample-clock origin, independent of microphone startup and network latency. */
export interface CaptureTiming {
  /** Estimated performance.now() of the first sample, before residual mic calibration. */
  startedAt: number
  durationMs: number
}

let releasing: Promise<void> | null = null

/**
 * Stream PCM without retaining it; reject missing audio, clock gaps and sample-rate changes.
 * @param durationMs Required audio duration, in milliseconds.
 * @param onChunk Consumer of mono PCM and its sample rate.
 * @param opts Source and cancellation settings.
 * @returns Timing of the samples delivered to the consumer.
 */
export async function captureAudio(
  durationMs: number, onChunk: (pcm: Float32Array, sampleRate: number) => void, opts: CaptureOptions = {},
): Promise<CaptureTiming> {
  if (!Number.isInteger(durationMs) || durationMs <= 0 || durationMs > 60_000) throw new RangeError('Capture duration must be within 1-60000 ms')
  if (releasing) throw new Error('Previous microphone session is still closing; wait or reopen the app')
  opts.signal?.throwIfAborted()
  const source = await createAudioSource(opts)
  let off = () => {}
  let cancel = () => {}
  let deadline: number | undefined
  let stalled: number | undefined
  try {
    return await new Promise<CaptureTiming>((resolve, reject) => {
      let sampleRate = 0
      let sampleCount = 0
      let startedAt: number | null = null
      let settled = false
      const fail = (reason: unknown) => {
        if (settled) return
        settled = true
        reject(reason)
      }
      cancel = () => fail(new DOMException('Listening cancelled', 'AbortError'))
      if (opts.signal?.aborted) { cancel(); return }
      opts.signal?.addEventListener('abort', cancel, { once: true })
      deadline = window.setTimeout(() => fail(new Error('Microphone capture timed out')), durationMs + 10_000)
      stalled = window.setTimeout(() => fail(new Error('No microphone audio received')), 8000)
      off = source.onAudioData((pcm, rate) => {
        if (settled || !pcm.length) return
        try {
          if (!Number.isFinite(rate) || rate < 8000 || rate > 96000 ||
              (sampleRate && rate !== sampleRate)) throw new Error('Invalid or changing microphone sample rate')
          if (pcm.some((value) => !Number.isFinite(value))) throw new Error('Invalid microphone samples')
          sampleRate = rate
          const now = performance.now()
          // Callbacks deliver completed blocks. Remove the block's own duration
          // before applying any user-calibrated residual hardware/transport delay.
          if (startedAt === null) startedAt = now - pcm.length * 1000 / rate
          const expectedEnd = startedAt + (sampleCount + pcm.length) * 1000 / rate
          if (Math.abs(now - expectedEnd) > 1000) throw new Error('Microphone audio has gaps or excessive buffering; retry sync')
          window.clearTimeout(stalled)
          stalled = window.setTimeout(() => fail(new Error('Microphone audio stopped')), 3000)
          const remaining = Math.round(durationMs * rate / 1000) - sampleCount
          const chunk = pcm.subarray(0, Math.min(remaining, pcm.length))
          onChunk(chunk, rate)
          sampleCount += chunk.length
          if (sampleCount >= Math.round(durationMs * rate / 1000)) {
            settled = true
            resolve({ startedAt, durationMs: sampleCount * 1000 / rate })
          }
        } catch (error) { fail(error) }
      })
      void source.start().catch(fail)
    })
  } finally {
    off()
    opts.signal?.removeEventListener('abort', cancel)
    window.clearTimeout(deadline)
    window.clearTimeout(stalled)
    const closing = Promise.resolve().then(() => source.dispose())
    releasing = closing
    void closing.then(() => { if (releasing === closing) releasing = null }, () => {})
    let cleanupTimer: number | undefined
    try {
      await Promise.race([closing, new Promise<never>((_, reject) => {
        cleanupTimer = window.setTimeout(() => reject(new Error('Could not confirm microphone shutdown; reopen the app')), 5000)
      })])
    } finally { window.clearTimeout(cleanupTimer) }
  }
}

let factoryOverride: ((opts: CaptureOptions) => Promise<Input>) | null = null

/** Replace microphone creation for the scenario harness; null restores real devices. */
export function setAudioSourceFactory(factory: ((opts: CaptureOptions) => Promise<Input>) | null): void {
  factoryOverride = factory
}

/** Select the SDK microphone or browser fallback; sidecar requires an explicit URL. */
export async function createAudioSource(opts: CaptureOptions = {}): Promise<Input> {
  if (factoryOverride) return factoryOverride(opts)
  const { preferredSource = 'glasses', sidecarUrl, bridgeWaitMs = 3000 } = opts
  if (preferredSource === 'sidecar') {
    if (!sidecarUrl) throw new Error('Sidecar URL not configured')
    return new WebSocketAudioSource(sidecarUrl)
  }
  const ready = isGlassReady() || await waitForGlassReady(bridgeWaitMs)
  return ready ? new GlassAudioSource(preferredSource === 'phone' ? AudioInputSource.Phone : AudioInputSource.Glasses)
    : new MicrophoneAudioSource()
}
