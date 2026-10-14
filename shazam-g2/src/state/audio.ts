import { GlassAudioSource, MicrophoneAudioSource, WebSocketAudioSource, type AudioSource as IAudioSource } from './audioSources'
import { isGlassReady, waitForGlassReady } from '../glass/bridgeState'
import type { AudioSource } from '../glass/shared'

/**
 * Capture ~`durationMs` of PCM and encode it as a 16 kHz mono S16LE WAV blob.
 *
 * `preferredSource` selects the audio path:
 *   - 'glasses' (default): try the G2 mic via the bridge; fall back to the
 *     browser mic if the bridge isn't ready within `bridgeWaitMs`.
 *   - 'phone': force the browser mic (only works in secure contexts —
 *     localhost dev or HTTPS).
 *   - 'sidecar': connect to the laptop sidecar at `VITE_SIDECAR_URL` and
 *     stream desktop-mic PCM over WebSocket.
 */
export interface RecordingResult {
  blob: Blob
  /** performance.now() timestamp of the first audio sample captured — use as clock anchor. */
  startedAt: number
}

export interface RecordOptions {
  preferredSource?: AudioSource
  sidecarUrl?: string
  bridgeWaitMs?: number
}

export async function recordGlassesAudio(durationMs = 10_000, opts: RecordOptions = {}): Promise<RecordingResult> {
  const { preferredSource = 'glasses', sidecarUrl, bridgeWaitMs = 3000 } = opts

  let source: IAudioSource
  let label: string
  if (preferredSource === 'sidecar') {
    if (!sidecarUrl) throw new Error('Sidecar URL not configured — set it in the web UI')
    source = new WebSocketAudioSource(sidecarUrl)
    label = `WebSocketAudioSource (sidecar ${sidecarUrl})`
  } else if (preferredSource === 'phone') {
    source = new MicrophoneAudioSource()
    label = 'MicrophoneAudioSource (forced phone)'
  } else {
    const bridgeReady = isGlassReady() || (await waitForGlassReady(bridgeWaitMs))
    source = bridgeReady ? new GlassAudioSource() : new MicrophoneAudioSource()
    label = bridgeReady ? 'GlassAudioSource (bridge)' : 'MicrophoneAudioSource (bridge unavailable, fell back)'
  }
  console.info('[audio] source:', label)
  const chunks: Float32Array[] = []
  let sampleRate = 16_000
  let startedAt = 0

  const off = source.onAudioData((pcm, sr) => {
    if (startedAt === 0) startedAt = performance.now()
    chunks.push(pcm)
    sampleRate = sr
  })

  try {
    await source.start()
    await new Promise((resolve) => setTimeout(resolve, durationMs))

    const mono = concatFloat32(chunks)
    const resampled = sampleRate === 16_000 ? mono : resampleTo16k(mono, sampleRate)
    const wav = float32ToWav(resampled, 16_000)
    return {
      blob: new Blob([wav], { type: 'audio/wav' }),
      startedAt: startedAt || performance.now(),
    }
  } finally {
    off()
    source.stop()
    source.dispose?.()
  }
}

function concatFloat32(chunks: Float32Array[]): Float32Array {
  let total = 0
  for (const c of chunks) total += c.length
  const out = new Float32Array(total)
  let offset = 0
  for (const c of chunks) {
    out.set(c, offset)
    offset += c.length
  }
  return out
}

function resampleTo16k(input: Float32Array, srcRate: number): Float32Array {
  const ratio = srcRate / 16_000
  const outLen = Math.floor(input.length / ratio)
  const out = new Float32Array(outLen)
  for (let i = 0; i < outLen; i++) {
    const srcIndex = i * ratio
    const i0 = Math.floor(srcIndex)
    const i1 = Math.min(i0 + 1, input.length - 1)
    const t = srcIndex - i0
    out[i] = input[i0] * (1 - t) + input[i1] * t
  }
  return out
}

function float32ToWav(samples: Float32Array, sampleRate: number): ArrayBuffer {
  const pcmBytes = samples.length * 2
  const buffer = new ArrayBuffer(44 + pcmBytes)
  const view = new DataView(buffer)

  writeAscii(view, 0, 'RIFF')
  view.setUint32(4, 36 + pcmBytes, true)
  writeAscii(view, 8, 'WAVE')
  writeAscii(view, 12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeAscii(view, 36, 'data')
  view.setUint32(40, pcmBytes, true)

  let offset = 44
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  return buffer
}

function writeAscii(view: DataView, offset: number, text: string) {
  for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i))
}
