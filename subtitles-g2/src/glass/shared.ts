import type { Cue, Timeline } from '../state/srt'

export type AppMode = 'empty' | 'ready' | 'searching' | 'playing' | 'paused'

export interface Film {
  /** Display name, taken from the imported file name. */
  name: string
  cues: Cue[]
  timeline: Timeline
  durationMs: number
}

export type AudioSource = 'glasses' | 'phone' | 'sidecar'
export type SyncEngine = 'asr' | 'offline'

export interface AppSnapshot {
  mode: AppMode
  film: Film | null
  /** Index into `film.timeline`; -1 before the first cue. */
  currentIndex: number
  /**
   * Playback position at the last transport change. Combined with `anchorAt`
   * this gives the current position without a per-tick counter.
   */
  positionMs: number
  /** performance.now() when playback last started; null while paused. */
  anchorAt: number | null
  /** Display-only adjustment in wall milliseconds; positive shows subtitles later. */
  offsetMs: number
  /**
   * Cue time advanced per millisecond of wall clock. Corrects a framerate
   * mismatch between the subtitle release and the screening.
   */
  rateFactor: number
  /**
   * Residual capture delay in wall milliseconds, after accounting for PCM block
   * duration. Added to sample-clock anchors; excludes cloud processing latency.
   */
  micLatencyMs: number
  /** Whether periodic microphone alignment is running. */
  autoSync: boolean
  syncEngine: SyncEngine
  syncBusy: boolean
  asrUrl: string
  /** Session-only credential for our token broker, never a permanent Soniox key. */
  asrAccessToken: string
  /** Session-only permission to send microphone audio to Soniox. */
  asrConsent: boolean
  /** Human-readable result of the last alignment attempt. */
  syncStatus: string | null
  /** Current interval between automatic checks, which widens while readings stay clean. */
  syncCadenceMs: number | null
  error: string | null
  audioSource: AudioSource
  sidecarUrl: string
}
