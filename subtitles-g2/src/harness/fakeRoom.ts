import { cueSignal } from '../state/align.ts'
import { setAudioSourceFactory } from '../state/audio.ts'
import type { AudioListener, AudioSource as IAudioSource } from '../state/audioSources.ts'
import type { Timeline } from '../state/srt.ts'
import { clock } from './env.ts'

/**
 * A synthetic auditorium.
 *
 * Models what the room is really playing at any moment, independent of what the
 * app believes. Audio is emitted bin by bin as virtual time passes, so a
 * scenario can start late, jump, pause, or run at the wrong speed and the
 * alignment code has to work it out from the audio alone.
 */

const SAMPLE_RATE = 16_000
const BIN_MS = 100
const SAMPLES_PER_BIN = (SAMPLE_RATE * BIN_MS) / 1000

export interface RoomPlan {
  timeline: Timeline
  /** Cue time the film is at when it starts. */
  startCueMs: number
  /**
   * Times below are measured from when the room was created, not from the
   * virtual clock's origin, so a scenario reads the same wherever it runs in a
   * sequence.
   */
  /** Delay before the film starts; until then the room plays unrelated audio. */
  startsAtMs?: number
  /** Playback speed, for framerate-mismatch scenarios. */
  rate?: number
  /** Position changes applied from a given time, e.g. a projectionist jump. */
  jumps?: { atMs: number; deltaMs: number }[]
  /** Intervals where the film is stopped. */
  pauses?: { fromMs: number; toMs: number }[]
  /** Intervals playing continuous score or ambience instead of dialogue. */
  musicIntervals?: { fromMs: number; toMs: number }[]
  /** Continuous score or effects sitting under the dialogue for the whole run. */
  bedLevel?: number
  /** Auditorium reverb tail, as the time for a sound to decay away. */
  reverbMs?: number
  /** Microphone automatic gain control, which compresses loud against quiet. */
  agc?: boolean
  /** Amplitude of additive noise on the envelope. */
  noise?: number
  /** Delay between sound leaving the speakers and reaching the microphone. */
  latencyMs?: number
}

export class FakeRoom {
  private seed = 1337
  private trailerRun = 0
  private trailerLoud = false
  private tail = 0
  private readonly plan: RoomPlan
  private readonly createdAt: number

  constructor(plan: RoomPlan) {
    this.plan = plan
    this.createdAt = clock.now()
  }

  /** Cue time playing in the room at a given virtual time, or null before the film starts. */
  cueTimeAt(virtualNow: number): number | null {
    const local = virtualNow - this.createdAt
    const startsAt = this.plan.startsAtMs ?? 0
    if (local < startsAt) return null

    let elapsed = local - startsAt
    for (const pause of this.plan.pauses ?? []) {
      if (local > pause.toMs) elapsed -= pause.toMs - pause.fromMs
      else if (local > pause.fromMs) elapsed -= local - pause.fromMs
    }

    let position = this.plan.startCueMs + elapsed * (this.plan.rate ?? 1)
    for (const jump of this.plan.jumps ?? []) {
      if (local >= jump.atMs) position += jump.deltaMs
    }
    return position
  }

  /** An `AudioSource` that streams the room's audio until stopped. */
  createSource(): IAudioSource {
    const listeners: AudioListener[] = []
    const room = this
    let timer: number | null = null
    let live = false

    const emit = () => {
      if (!live) return
      // Sound arriving now left the speakers a moment ago.
      const at = clock.now() - BIN_MS - (room.plan.latencyMs ?? 0)
      const level = room.levelAt(at)
      // Noise carried at that level, not a constant: a real microphone hears a
      // signal with content across the band, and the capture path filters it.
      const chunk = new Float32Array(SAMPLES_PER_BIN)
      for (let i = 0; i < chunk.length; i++) chunk[i] = level * (room.random() * 2 - 1)
      for (const cb of listeners) cb(chunk, SAMPLE_RATE)
      timer = clock.setTimeout(emit, BIN_MS)
    }

    return {
      async start(): Promise<void> {
        live = true
        timer = clock.setTimeout(emit, BIN_MS)
      },
      stop(): void {
        live = false
        if (timer !== null) clock.clearTimeout(timer)
        timer = null
      },
      onAudioData(cb: AudioListener): () => void {
        listeners.push(cb)
        return () => {
          const i = listeners.indexOf(cb)
          if (i >= 0) listeners.splice(i, 1)
        }
      },
      dispose(): void {
        listeners.length = 0
      },
    }
  }

  /** Whether the room is playing continuous score or ambience at this moment. */
  isMusicAt(virtualNow: number): boolean {
    const local = virtualNow - this.createdAt
    return (this.plan.musicIntervals ?? []).some((m) => local >= m.fromMs && local < m.toMs)
  }

  /** Continuous sound: loud throughout, so the envelope has almost no contrast. */
  musicAmplitude(): number {
    return Math.abs(0.55 + (this.random() - 0.5) * 0.08)
  }

  /** Level the microphone hears for one bin, after reverb and microphone gain control. */
  private levelAt(virtualNow: number): number {
    const dry = this.isMusicAt(virtualNow)
      ? this.musicAmplitude()
      : this.amplitudeFor(this.cueTimeAt(virtualNow))

    const reverb = this.plan.reverbMs ?? 0
    this.tail = reverb > 0 ? Math.max(dry, this.tail * Math.exp(-BIN_MS / reverb)) : dry
    // Gain control pulls quiet and loud together without erasing the pattern.
    return this.plan.agc ? Math.sqrt(this.tail) : this.tail
  }

  /** Envelope amplitude for one bin: dialogue is loud, gaps are quiet, everything is noisy. */
  private amplitudeFor(cueTime: number | null): number {
    const bed = this.plan.bedLevel ?? 0
    const noise = (this.random() - 0.5) * (this.plan.noise ?? 0.15)
    // Unrelated audio: trailers and ads have their own speech rhythm, so this
    // has to be rejected by correlation rather than by looking featureless.
    if (cueTime === null) return Math.abs(this.unrelatedSpeech() * 0.8 + 0.1 + bed + noise)

    const signal = cueSignal(this.plan.timeline, cueTime, BIN_MS, 1)[0]
    return Math.abs(signal * 0.8 + 0.1 + bed + noise)
  }

  /** A speech/silence pattern with plausible run lengths, unrelated to the film. */
  private unrelatedSpeech(): number {
    if (this.trailerRun <= 0) {
      this.trailerRun = 3 + Math.floor(this.random() * 25)
      this.trailerLoud = !this.trailerLoud
    }
    this.trailerRun--
    return this.trailerLoud ? 1 : 0
  }

  /** Deterministic noise, so a failing scenario reproduces exactly. */
  private random(): number {
    this.seed = (this.seed * 1103515245 + 12345) % 2147483648
    return this.seed / 2147483648
  }
}

/** Route every capture through the given room for the rest of the run. */
export function installFakeRoom(room: FakeRoom): void {
  setAudioSourceFactory(async () => room.createSource())
}
