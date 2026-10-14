import { AudioInputSource, waitForEvenAppBridge, type EvenAppBridge } from '@evenrealities/even_hub_sdk'

export type AudioListener = (pcm: Float32Array, sampleRate: number) => void

export interface AudioSource {
  start(): Promise<void>
  stop(): void | Promise<void>
  onAudioData(cb: AudioListener): () => void
  dispose(): void | Promise<void>
}

const GLASS_SAMPLE_RATE = 16_000

/**
 * Reads 16kHz mono S16LE PCM from the glasses or phone microphone via the raw SDK bridge.
 *
 * @param input Which host microphone to open; the phone mic needs SDK >= 0.0.11.
 */
export class GlassAudioSource implements AudioSource {
  private bridge: EvenAppBridge | null = null
  private listeners: AudioListener[] = []
  private unsubscribe: (() => void) | null = null
  private listening = false
  private disposed = false
  private opening: Promise<boolean> | null = null
  private closing: Promise<void> | null = null
  private readonly input: AudioInputSource

  constructor(input: AudioInputSource = AudioInputSource.Glasses) {
    this.input = input
  }

  async start(): Promise<void> {
    if (this.listening) return
    this.bridge = await waitForEvenAppBridge()
    if (this.disposed) return
    // Subscribe before audioControl so we don't miss the first events,
    // but gate dispatch on `listening` and clean up if audioControl fails.
    this.unsubscribe = this.bridge.onEvenHubEvent((event) => {
      if (!this.listening) return
      const pcm = event?.audioEvent?.audioPcm
      if (!pcm || pcm.length === 0) return
      const f32 = pcm16ToFloat32(pcm)
      for (const cb of this.listeners) cb(f32, GLASS_SAMPLE_RATE)
    })
    this.listening = true
    this.opening = this.bridge.audioControl(true, this.input)
    try {
      if (!await this.opening) throw new Error('Microphone permission denied or microphone unavailable')
    } catch (err) {
      this.listening = false
      this.unsubscribe?.()
      this.unsubscribe = null
      throw err
    }
  }

  stop(): Promise<void> {
    this.disposed = true
    this.listening = false
    this.unsubscribe?.()
    this.unsubscribe = null
    // Serialize close after open, including a late native permission response.
    this.closing ??= (async () => {
      await this.opening?.catch(() => false)
      if (this.bridge && this.opening && !await this.bridge.audioControl(false)) {
        throw new Error('Could not confirm microphone shutdown')
      }
    })()
    return this.closing
  }

  onAudioData(cb: AudioListener): () => void {
    this.listeners.push(cb)
    return () => {
      const i = this.listeners.indexOf(cb)
      if (i >= 0) this.listeners.splice(i, 1)
    }
  }

  async dispose(): Promise<void> {
    this.listeners.length = 0
    await this.stop()
  }
}

/** Reads mono Float32 PCM from the browser microphone — dev fallback only. */
export class MicrophoneAudioSource implements AudioSource {
  private stream: MediaStream | null = null
  private ctx: AudioContext | null = null
  private script: ScriptProcessorNode | null = null
  private sourceNode: MediaStreamAudioSourceNode | null = null
  private listeners: AudioListener[] = []
  private disposed = false

  async start(): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('getUserMedia unavailable — use the glasses mic or a different environment.')
    }
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: GLASS_SAMPLE_RATE,
        channelCount: 1,
        // Applies to browser fallback only; SDK microphones have their own processing.
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
    })
    if (this.disposed) { this.stop(); return }
    this.ctx = new AudioContext({ sampleRate: GLASS_SAMPLE_RATE })
    this.sourceNode = this.ctx.createMediaStreamSource(this.stream)
    this.script = this.ctx.createScriptProcessor(4096, 1, 1)
    this.script.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0)
      const chunk = new Float32Array(input.length)
      chunk.set(input)
      const rate = this.ctx?.sampleRate ?? GLASS_SAMPLE_RATE
      for (const cb of this.listeners) cb(chunk, rate)
    }
    this.sourceNode.connect(this.script)
    this.script.connect(this.ctx.destination)
    await this.ctx.resume()
  }

  stop(): void {
    this.disposed = true
    if (this.script) {
      this.script.onaudioprocess = null
      this.script.disconnect()
      this.script = null
    }
    if (this.sourceNode) {
      this.sourceNode.disconnect()
      this.sourceNode = null
    }
    if (this.stream) {
      for (const t of this.stream.getTracks()) t.stop()
      this.stream = null
    }
    if (this.ctx) {
      this.ctx.close().catch(() => { /* ignore */ })
      this.ctx = null
    }
  }

  onAudioData(cb: AudioListener): () => void {
    this.listeners.push(cb)
    return () => {
      const i = this.listeners.indexOf(cb)
      if (i >= 0) this.listeners.splice(i, 1)
    }
  }

  dispose(): void {
    this.stop()
    this.listeners.length = 0
  }
}

function pcm16ToFloat32(bytes: Uint8Array): Float32Array {
  const samples = Math.floor(bytes.length / 2)
  const out = new Float32Array(samples)
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  for (let i = 0; i < samples; i++) out[i] = view.getInt16(i * 2, true) / 32768
  return out
}

/**
 * Reads 16 kHz mono S16LE PCM frames from the laptop sidecar via WebSocket.
 * Development source for microphone-assisted subtitle synchronization.
 */
export class WebSocketAudioSource implements AudioSource {
  private ws: WebSocket | null = null
  private listeners: AudioListener[] = []
  private connected = false
  private trailingByte: number | null = null
  private disposed = false
  private readonly url: string

  constructor(url: string) {
    this.url = url
  }

  start(): Promise<void> {
    if (this.connected) return Promise.resolve()
    return new Promise((resolve, reject) => {
      let settled = false
      const ws = new WebSocket(this.url)
      this.ws = ws
      ws.binaryType = 'arraybuffer'
      ws.onopen = () => {
        if (this.disposed) { ws.close(); reject(new Error('Sidecar capture cancelled')); return }
        this.connected = true
        settled = true
        resolve()
      }
      ws.onmessage = (event) => {
        if (!this.connected) return
        if (typeof event.data === 'string') return
        let bytes = new Uint8Array(event.data as ArrayBuffer)
        if (bytes.length === 0) return
        if (this.trailingByte !== null) {
          const joined = new Uint8Array(bytes.length + 1)
          joined[0] = this.trailingByte
          joined.set(bytes, 1)
          bytes = joined
        }
        this.trailingByte = bytes.length % 2 ? bytes[bytes.length - 1] : null
        const f32 = pcm16ToFloat32(bytes)
        for (const cb of this.listeners) cb(f32, GLASS_SAMPLE_RATE)
      }
      ws.onerror = () => {
        if (!settled) {
          settled = true
          reject(new Error(`Sidecar connection failed: ${this.url}`))
        }
      }
      ws.onclose = () => {
        this.connected = false
        if (!settled) {
          settled = true
          reject(new Error(`Sidecar closed before connect: ${this.url}`))
        }
      }
    })
  }

  stop(): void {
    this.disposed = true
    this.connected = false
    if (this.ws) {
      try { this.ws.close() } catch { /* ignore */ }
      this.ws = null
    }
  }

  onAudioData(cb: AudioListener): () => void {
    this.listeners.push(cb)
    return () => {
      const i = this.listeners.indexOf(cb)
      if (i >= 0) this.listeners.splice(i, 1)
    }
  }

  dispose(): void {
    this.stop()
    this.listeners.length = 0
  }
}
