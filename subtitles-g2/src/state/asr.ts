import { captureAudio, type CaptureOptions, type CaptureTiming } from './capture'
import { segmentWords, type TranscriptWord } from './transcript'

/** Cloud recognition settings; broker credentials are unused when a direct key is configured. */
export interface AsrOptions extends CaptureOptions {
  tokenUrl: string
  accessToken: string
  /** Optional direct credential; otherwise use the key included at build time. */
  apiKey?: string
}

/** Final transcript plus the local sample-clock origin used by its timestamps. */
export interface Recognition extends CaptureTiming {
  words: TranscriptWord[]
}

type Token = { text: string; start_ms: number; end_ms: number; confidence: number }
const SONIOX_SOCKET = 'wss://stt-rt.soniox.com/transcribe-websocket'
const BUNDLED_ASR_KEY = import.meta.env?.VITE_SONIOX_API_KEY?.trim() ?? ''
const BUNDLED_ASR_MODEL = import.meta.env?.VITE_SONIOX_MODEL?.trim() || 'stt-rt-v5'

/** Whether this internal build includes a Soniox credential and needs no token broker. */
export const HAS_BUNDLED_ASR_KEY = BUNDLED_ASR_KEY.length > 0

/**
 * Transcribe one bounded PCM window using the bundled key or a broker-issued key.
 * @param durationMs Audio duration, excluding startup, network and finalization time.
 * @param opts Microphone, broker credentials and cancellation settings.
 * @returns Final words timed against the first captured sample.
 */
export async function transcribeLive(durationMs: number, opts: AsrOptions): Promise<Recognition> {
  const controller = new AbortController()
  const cancel = () => controller.abort(opts.signal?.reason)
  opts.signal?.addEventListener('abort', cancel, { once: true })
  if (opts.signal?.aborted) cancel()
  const timeout = window.setTimeout(() => controller.abort(new Error('Speech recognition timed out')), durationMs + 35_000)
  let socket: WebSocket | undefined
  try {
    const key = await getCredentials(opts, controller.signal)
    controller.signal.throwIfAborted()
    socket = new WebSocket(SONIOX_SOCKET)
    const ws = socket
    let openResolve: () => void = () => {}
    let openReject: (error: unknown) => void = () => {}
    const opened = new Promise<void>((resolve, reject) => { openResolve = resolve; openReject = reject })
    let finishResolve: () => void = () => {}
    let finishReject: (error: unknown) => void = () => {}
    const finished = new Promise<void>((resolve, reject) => { finishResolve = resolve; finishReject = reject })
    // Both promises can fail while the caller is awaiting the other phase.
    void opened.catch(() => {})
    void finished.catch(() => {})
    let ended = false
    let complete = false
    let configured = false
    let processedMs = 0
    let textLength = 0
    const tokens: Token[] = []
    const fail = (error: unknown) => {
      openReject(error)
      finishReject(error)
      controller.abort(error)
    }
    controller.signal.addEventListener('abort', () => {
      openReject(controller.signal.reason)
      finishReject(controller.signal.reason)
      ws.close()
    }, { once: true })
    ws.onopen = openResolve
    ws.onerror = () => fail(new Error('Speech recognition connection failed'))
    ws.onclose = () => { if (!complete) fail(new Error('Speech recognition connection closed before completion')) }
    ws.onmessage = (event) => {
      try {
        if (typeof event.data !== 'string' || event.data.length > 1_000_000) throw new Error('Invalid speech recognition message')
        const data: unknown = JSON.parse(event.data)
        if (!isRecord(data)) throw new Error('Invalid speech recognition response')
        if (data.error_code || data.error_type) throw new Error('Soniox rejected the session; check server model, credits and limits')
        if (typeof data.final_audio_proc_ms === 'number' && Number.isFinite(data.final_audio_proc_ms) &&
            data.final_audio_proc_ms >= 0 && data.final_audio_proc_ms <= durationMs + 1000) processedMs = data.final_audio_proc_ms
        if (Array.isArray(data.tokens)) {
          for (const token of data.tokens) {
            if (!isRecord(token) || token.is_final !== true) continue
            if (typeof token.text !== 'string' || /^<[^>]+>$/.test(token.text)) continue
            if (typeof token.start_ms !== 'number' || typeof token.end_ms !== 'number' ||
                typeof token.confidence !== 'number' || !Number.isFinite(token.start_ms) ||
                !Number.isFinite(token.end_ms) || !Number.isFinite(token.confidence) ||
                token.start_ms < 0 || token.end_ms < token.start_ms || token.end_ms > durationMs + 1000 ||
                token.confidence < 0 || token.confidence > 1) continue
            tokens.push({ text: token.text, start_ms: token.start_ms, end_ms: token.end_ms, confidence: token.confidence })
            textLength += token.text.length
            if (tokens.length > 4000 || textLength > 40_000) throw new Error('Speech recognition response exceeds capture budget')
          }
        }
        if (data.finished === true) {
          if (!ended || processedMs < durationMs - 500) throw new Error('Speech recognition did not process the full capture')
          complete = true
          finishResolve()
        }
      } catch (error) { fail(error) }
    }
    await opened
    const timing = await captureAudio(durationMs, (pcm, sampleRate) => {
      controller.signal.throwIfAborted()
      if (ws.readyState !== WebSocket.OPEN) throw new Error('Speech recognition stream is unavailable')
      if (ws.bufferedAmount > 512_000) throw new Error('Network too slow for speech recognition')
      if (!configured) {
        ws.send(JSON.stringify({ api_key: key.api_key, model: key.model,
          audio_format: 'pcm_s16le', sample_rate: sampleRate, num_channels: 1 }))
        configured = true
      }
      const bytes = new ArrayBuffer(pcm.length * 2)
      const view = new DataView(bytes)
      pcm.forEach((sample, i) => view.setInt16(i * 2, Math.round(Math.max(-1, Math.min(1, sample)) * 32767), true))
      ws.send(bytes)
    }, { ...opts, signal: controller.signal })
    ended = true
    ws.send('')
    await finished
    return { ...timing, words: tokensToWords(tokens) }
  } finally {
    window.clearTimeout(timeout)
    opts.signal?.removeEventListener('abort', cancel)
    socket?.close()
  }
}

/** Combine final subword tokens without inventing timestamps inside subtitle cues. */
export function tokensToWords(tokens: Token[]): TranscriptWord[] {
  let text = ''
  const spans = tokens.map((token) => {
    const from = text.length
    text += token.text
    return { from, to: text.length, token }
  })
  let index = 0
  return segmentWords(text).map((word) => {
    while (index + 1 < spans.length && spans[index].to <= word.index) index++
    const first = spans[index].token
    let last = index
    let confidence = first.confidence
    while (last + 1 < spans.length && spans[last + 1].from < word.index + word.text.length) {
      confidence = Math.min(confidence, spans[++last].token.confidence)
    }
    return { text: word.text, startMs: first.start_ms, endMs: spans[last].token.end_ms, confidence }
  })
}

async function getCredentials(opts: AsrOptions, signal: AbortSignal): Promise<{ api_key: string; model: string }> {
  signal.throwIfAborted()
  const directKey = opts.apiKey?.trim() || BUNDLED_ASR_KEY
  if (directKey) return { api_key: directKey, model: BUNDLED_ASR_MODEL }

  const url = new URL(opts.tokenUrl, window.location.href)
  const sameOrigin = url.origin === window.location.origin
  const localHost = url.hostname === 'localhost' || url.hostname === '[::1]' ||
    (/^\d+\.\d+\.\d+\.\d+$/.test(url.hostname) && /^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(url.hostname))
  if (url.username || url.password || url.hash || url.search ||
      (url.protocol !== 'https:' && !(sameOrigin && localHost && url.protocol === 'http:'))) {
    throw new Error('Token endpoint must use HTTPS (same-origin HTTP is allowed for local development)')
  }
  if (!opts.accessToken) throw new Error('Enter your sync-server access token first')
  const response = await fetch(url, {
    method: 'POST', headers: { Authorization: `Bearer ${opts.accessToken}` },
    cache: 'no-store', credentials: 'omit', referrerPolicy: 'no-referrer',
    redirect: 'error', signal,
  })
  if (!response.ok) throw new Error(`Sync authentication failed (${response.status})`)
  const key: unknown = await response.json()
  if (!isRecord(key) || typeof key.api_key !== 'string' || !key.api_key ||
      typeof key.model !== 'string' || !/^stt-rt-[a-z0-9-]+$/.test(key.model)) {
    throw new Error('Invalid sync-server response')
  }
  return { api_key: key.api_key, model: key.model }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
