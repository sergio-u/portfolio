import type { AppMode, AppSnapshot, AudioSource, Film, SyncEngine } from '../glass/shared'
import { persistentGet, persistentSet } from './persistentStorage'

type Listener = () => void

const AUDIO_SOURCE_KEY = 'subtitles-g2:audio-source'
const OFFSET_KEY = 'subtitles-g2:offset-ms'
const MIC_LATENCY_KEY = 'subtitles-g2:mic-latency-ms'
const ENGINE_KEY = 'subtitles-g2:sync-engine'
export const SIDECAR_URL_KEY = 'subtitles-g2:sidecar-url'
export const ASR_URL_KEY = 'subtitles-g2:asr-url'

function loadAudioSource(): AudioSource {
  try {
    const raw = window.localStorage.getItem(AUDIO_SOURCE_KEY)
    if (raw === 'phone' || raw === 'sidecar' || raw === 'glasses') return raw
    return 'glasses'
  } catch {
    return 'glasses'
  }
}

function loadOffsetMs(): number {
  try {
    const raw = Number(window.localStorage.getItem(OFFSET_KEY))
    return Number.isFinite(raw) ? raw : 0
  } catch {
    return 0
  }
}

function loadMicLatencyMs(): number {
  try {
    const raw = Number(window.localStorage.getItem(MIC_LATENCY_KEY))
    return Number.isFinite(raw) ? raw : 0
  } catch {
    return 0
  }
}

function loadSidecarUrl(): string {
  const raw = persistentGet(SIDECAR_URL_KEY)
  if (raw !== null) return raw
  // Bare `import.meta.env` so the value is still substituted at build time, while
  // staying readable outside a bundler.
  const env = import.meta.env as Record<string, string | undefined> | undefined
  return env?.VITE_SIDECAR_URL ?? ''
}

let snapshot: AppSnapshot = {
  mode: 'empty',
  film: null,
  currentIndex: -1,
  positionMs: 0,
  anchorAt: null,
  offsetMs: loadOffsetMs(),
  rateFactor: 1,
  micLatencyMs: loadMicLatencyMs(),
  autoSync: false,
  syncEngine: persistentGet(ENGINE_KEY) === 'offline' ? 'offline' : 'asr',
  syncBusy: false,
  asrUrl: persistentGet(ASR_URL_KEY) ?? '/api/asr-token',
  asrAccessToken: '',
  asrConsent: false,
  syncStatus: null,
  syncCadenceMs: null,
  error: null,
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

let syncRevision = 0
const SYNC_INPUTS: (keyof AppSnapshot)[] = ['film', 'mode', 'positionMs', 'anchorAt',
  'offsetMs', 'rateFactor', 'micLatencyMs', 'audioSource', 'sidecarUrl', 'syncEngine',
  'asrUrl', 'asrAccessToken', 'asrConsent']

/** Monotonic revision invalidates captures even when settings change and then change back. */
export function getSyncRevision(): number { return syncRevision }

function set(next: Partial<AppSnapshot>) {
  if (SYNC_INPUTS.some((key) => key in next && next[key] !== snapshot[key])) syncRevision++
  snapshot = { ...snapshot, ...next }
  for (const l of listeners) l()
}

export function setMode(mode: AppMode) {
  if (snapshot.mode === mode) return
  set({ mode })
}

/** Load a parsed film and reset the transport to its start. */
export function setFilm(film: Film | null) {
  set({
    film,
    autoSync: false,
    mode: film ? 'ready' : 'empty',
    currentIndex: -1,
    positionMs: 0,
    anchorAt: null,
    rateFactor: 1,
    syncStatus: null,
    error: null,
  })
}

export function setRateFactor(rateFactor: number) {
  if (!Number.isFinite(rateFactor) || rateFactor < 0.9 || rateFactor > 1.1 || snapshot.rateFactor === rateFactor) return
  // Preserve current position when changing rate while playing.
  const now = performance.now()
  const positionMs = snapshot.positionMs + (snapshot.anchorAt === null ? 0 : (now - snapshot.anchorAt) * snapshot.rateFactor)
  set({ rateFactor, positionMs, anchorAt: snapshot.anchorAt === null ? null : now })
}

export function setAutoSync(autoSync: boolean) {
  if (snapshot.autoSync === autoSync) return
  set({ autoSync })
}

export function setMicLatencyMs(micLatencyMs: number) {
  if (!Number.isFinite(micLatencyMs) || micLatencyMs < 0 || micLatencyMs > 5000 || snapshot.micLatencyMs === micLatencyMs) return
  try {
    window.localStorage.setItem(MIC_LATENCY_KEY, String(micLatencyMs))
  } catch {
    // ignore
  }
  set({ micLatencyMs })
}

/** Choose cloud recognition or the explicit experimental offline matcher. */
export function setSyncEngine(syncEngine: SyncEngine) {
  if (snapshot.syncEngine === syncEngine) return
  persistentSet(ENGINE_KEY, syncEngine)
  set({ syncEngine, autoSync: false, syncStatus: null })
}

/** Set the broker address; no credentials belong in this URL. */
export function setAsrUrl(asrUrl: string) {
  if (snapshot.asrUrl === asrUrl) return
  persistentSet(ASR_URL_KEY, asrUrl)
  set({ asrUrl })
}

/** Keep broker credentials in memory only. */
export function setAsrAccessToken(asrAccessToken: string) { set({ asrAccessToken }) }

/** Grant or revoke cloud-audio permission for this app session. */
export function setAsrConsent(asrConsent: boolean) { set({ asrConsent, autoSync: false }) }

/** Publish whether a sync request owns the microphone. */
export function setSyncBusy(syncBusy: boolean) { set({ syncBusy }) }

export function setSyncCadenceMs(syncCadenceMs: number | null) {
  if (snapshot.syncCadenceMs === syncCadenceMs) return
  set({ syncCadenceMs })
}

export function setSyncStatus(syncStatus: string | null) {
  if (snapshot.syncStatus === syncStatus) return
  set({ syncStatus })
}

export function setCurrentIndex(currentIndex: number) {
  if (snapshot.currentIndex === currentIndex) return
  set({ currentIndex })
}

export function setTransport(next: { mode: AppMode; positionMs: number; anchorAt: number | null }) {
  set(next)
}

export function setOffsetMs(offsetMs: number) {
  if (!Number.isFinite(offsetMs) || snapshot.offsetMs === offsetMs) return
  try {
    window.localStorage.setItem(OFFSET_KEY, String(offsetMs))
  } catch {
    // ignore — runtime value still applies for this session
  }
  set({ offsetMs })
}

export function setError(error: string | null) {
  if (snapshot.error === error) return
  set({ error })
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
