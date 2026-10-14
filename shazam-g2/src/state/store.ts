import type {
  AppMode,
  AppSnapshot,
  AudioSource,
  PlainLyrics,
  RecognizerProvider,
  SyncedLyrics,
  Track,
} from '../glass/shared'
import { persistentGet, persistentSet } from './persistentStorage'

type Listener = () => void

const SHOW_LYRICS_KEY = 'shazam-g2:show-lyrics'
const PROVIDER_KEY = 'shazam-g2:provider'
const SCROBBLE_ENABLED_KEY = 'shazam-g2:scrobble-enabled'
const AUDIO_SOURCE_KEY = 'shazam-g2:audio-source'
export const SIDECAR_URL_KEY = 'shazam-g2:sidecar-url'

function loadShowLyrics(): boolean {
  try {
    const raw = window.localStorage.getItem(SHOW_LYRICS_KEY)
    return raw === null ? false : raw === 'true'
  } catch {
    return false
  }
}

function loadScrobbleEnabled(): boolean {
  try {
    const raw = window.localStorage.getItem(SCROBBLE_ENABLED_KEY)
    return raw === null ? true : raw === 'true'
  } catch {
    return true
  }
}

function loadProvider(): RecognizerProvider {
  try {
    const raw = window.localStorage.getItem(PROVIDER_KEY)
    return raw === 'audd' ? 'audd' : 'acrcloud'
  } catch {
    return 'acrcloud'
  }
}

function loadAudioSource(): AudioSource {
  try {
    const raw = window.localStorage.getItem(AUDIO_SOURCE_KEY)
    if (raw === 'phone' || raw === 'sidecar' || raw === 'glasses') return raw
    return 'glasses'
  } catch {
    return 'glasses'
  }
}

function loadSidecarUrl(): string {
  const raw = persistentGet(SIDECAR_URL_KEY)
  if (raw !== null) return raw
  return (import.meta.env.VITE_SIDECAR_URL as string | undefined) ?? ''
}

let snapshot: AppSnapshot = {
  mode: 'idle',
  track: null,
  lyrics: null,
  error: null,
  showLyrics: loadShowLyrics(),
  provider: loadProvider(),
  scrobbleEnabled: loadScrobbleEnabled(),
  audioSource: loadAudioSource(),
  sidecarUrl: loadSidecarUrl(),
}

const listeners = new Set<Listener>()

export function getAppSnapshot(): AppSnapshot {
  return snapshot
}

export function subscribe(l: Listener): () => void {
  listeners.add(l)
  return () => listeners.delete(l)
}

function set(next: Partial<AppSnapshot>) {
  snapshot = { ...snapshot, ...next }
  for (const l of listeners) l()
}

export function setMode(mode: AppMode) {
  if (snapshot.mode === mode) return
  set({ mode })
}

export function setTrack(track: Track | null) {
  set({ track })
}

export function setLyrics(lyrics: SyncedLyrics | PlainLyrics | null) {
  set({ lyrics })
}

export function setLyricIndex(index: number) {
  const current = snapshot.lyrics
  if (!current) return
  if (current.currentIndex === index) return
  set({ lyrics: { ...current, currentIndex: index } })
}

export function setScrollMode(mode: 'auto' | 'manual') {
  const current = snapshot.lyrics
  if (!current || current.kind !== 'synced') return
  if (current.scrollMode === mode) return
  set({ lyrics: { ...current, scrollMode: mode } })
}

export function moveLyricIndex(delta: number) {
  const current = snapshot.lyrics
  if (!current) return
  const max = current.lines.length - 1
  if (max < 0) return
  const next = Math.max(0, Math.min(max, current.currentIndex + delta))
  if (next === current.currentIndex) return
  const lyrics =
    current.kind === 'synced'
      ? { ...current, currentIndex: next, scrollMode: 'manual' as const }
      : { ...current, currentIndex: next }
  set({ lyrics })
}

export function setError(error: string | null) {
  if (snapshot.error === error) return
  set({ error })
}

export function setShowLyrics(showLyrics: boolean) {
  if (snapshot.showLyrics === showLyrics) return
  try {
    window.localStorage.setItem(SHOW_LYRICS_KEY, String(showLyrics))
  } catch {
    // ignore — non-fatal, runtime preference still applies for this session
  }
  set({ showLyrics })
}

export function setProvider(provider: RecognizerProvider) {
  if (snapshot.provider === provider) return
  try {
    window.localStorage.setItem(PROVIDER_KEY, provider)
  } catch {
    // ignore
  }
  set({ provider })
}

export function setScrobbleEnabled(scrobbleEnabled: boolean) {
  if (snapshot.scrobbleEnabled === scrobbleEnabled) return
  try {
    window.localStorage.setItem(SCROBBLE_ENABLED_KEY, String(scrobbleEnabled))
  } catch {
    // ignore
  }
  set({ scrobbleEnabled })
}

export function setAudioSource(audioSource: AudioSource) {
  if (snapshot.audioSource === audioSource) return
  try {
    window.localStorage.setItem(AUDIO_SOURCE_KEY, audioSource)
  } catch {
    // ignore
  }
  set({ audioSource })
}

export function setSidecarUrl(sidecarUrl: string) {
  if (snapshot.sidecarUrl === sidecarUrl) return
  persistentSet(SIDECAR_URL_KEY, sidecarUrl)
  set({ sidecarUrl })
}

export function reset() {
  set({ mode: 'idle', track: null, lyrics: null, error: null })
}
