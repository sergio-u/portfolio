export type AppMode =
  | 'idle'
  | 'listening'
  | 'recognizing'
  | 'fetching-lyrics'
  | 'playing-synced'
  | 'playing-plain'
  | 'metadata-only'
  | 'no-match'
  | 'error'

export interface Track {
  title: string
  artist: string
  album?: string
  durationMs?: number
  timecodeMs: number
  /** performance.now() at recording start — lyric-clock anchor. */
  recognizedAt: number
}

export interface SyncedLyrics {
  kind: 'synced'
  lines: [number, string][]
  currentIndex: number
  scrollMode: 'auto' | 'manual'
}

export interface PlainLyrics {
  kind: 'plain'
  lines: string[]
  currentIndex: number
}

export type RecognizerProvider = 'audd' | 'acrcloud'

export type AudioSource = 'glasses' | 'phone' | 'sidecar'

export interface AppSnapshot {
  mode: AppMode
  track: Track | null
  lyrics: SyncedLyrics | PlainLyrics | null
  error: string | null
  showLyrics: boolean
  provider: RecognizerProvider
  scrobbleEnabled: boolean
  audioSource: AudioSource
  sidecarUrl: string
}
