import { recordGlassesAudio } from './audio'
import * as audd from './audd'
import * as acrcloud from './acrcloud'
import { loadLastfmConfig, loadSession, scrobble } from './lastfm'
import { fetchPlainLyrics, fetchSyncedLyrics } from './lyrics'
import { startLyricsClock } from './clock'
import {
  getAppSnapshot,
  reset as storeReset,
  setError,
  setLyricIndex,
  setLyrics,
  setMode,
  setScrollMode,
  setTrack,
} from './store'
import type { Track } from '../glass/shared'

type Navigate = (path: string) => void

export interface Pipeline {
  runRecognition: () => Promise<void>
  resyncLyrics: () => void
  pauseLyrics: () => void
  reset: () => void
}

let stopClock: (() => void) | null = null
let inFlight = false
// Bumped by reset() and on each recognition start so an in-flight run that
// was made obsolete (user reset or re-tapped through a stuck guard) can bail
// after each await instead of clobbering newer state.
let runIdCounter = 0
let dimTimer: ReturnType<typeof setTimeout> | null = null
const DIM_TIMEOUT_MS = 30_000
let shared: Pipeline | null = null

export function getPipeline(): Pipeline | null {
  return shared
}

export function createPipeline(navigate: Navigate): Pipeline {
  async function runRecognition() {
    if (inFlight) return
    const myRun = ++runIdCounter
    const isStale = () => myRun !== runIdCounter

    try {
      inFlight = true
      teardownClock()
      teardownDimTimer()
      storeReset()

      setMode('listening')
      navigate('/listening')

      const { blob, startedAt } = await recordGlassesAudio(10_000, {
        preferredSource: getAppSnapshot().audioSource,
        sidecarUrl: getAppSnapshot().sidecarUrl,
      })
      if (isStale()) return

      setMode('recognizing')
      navigate('/searching')

      const recognizers = { audd, acrcloud } as const
      const provider = getAppSnapshot().provider
      const r = recognizers[provider]
      if (!r.isConfigured()) {
        throw new Error(`${provider} is selected but not configured — check .env.local`)
      }
      console.log('[pipeline] recognizing with', provider)
      const track = await r.recognize(blob, startedAt)
      if (isStale()) return
      console.log('[pipeline] result', track ?? 'no match')

      if (!track) {
        setError('No match found')
        setMode('no-match')
        navigate('/nomatch')
        return
      }

      setTrack(track)
      if (getAppSnapshot().scrobbleEnabled) void scrobbleRecognition(track)

      if (!getAppSnapshot().showLyrics) {
        setMode('metadata-only')
        navigate('/nowplaying')
        scheduleDim()
        return
      }

      setMode('fetching-lyrics')

      const synced = await fetchSyncedLyrics(track).catch((err) => {
        console.warn('[pipeline] synced lyrics fetch failed:', err)
        return null
      })
      if (isStale()) return
      if (synced) {
        setLyrics(synced)
        setMode('playing-synced')
        navigate('/nowplaying')
        startClock()
        return
      }

      const plain = await fetchPlainLyrics(track).catch((err) => {
        console.warn('[pipeline] plain lyrics fetch failed:', err)
        return null
      })
      if (isStale()) return
      if (plain) {
        setLyrics(plain)
        setMode('playing-plain')
        navigate('/nowplaying')
        return
      }

      setMode('metadata-only')
      navigate('/nowplaying')
      scheduleDim()
    } catch (err) {
      if (isStale()) return
      console.error('[pipeline] recognition failed:', err)
      const message = err instanceof Error ? err.message : 'Recognition failed'
      setError(message)
      setMode('error')
      navigate('/nomatch')
    } finally {
      inFlight = false
    }
  }

  function resyncLyrics() {
    const snap = getAppSnapshot()
    if (snap.lyrics?.kind !== 'synced') return
    setScrollMode('auto')
    startClock()
  }

  function pauseLyrics() {
    const snap = getAppSnapshot()
    if (snap.lyrics?.kind !== 'synced') return
    teardownClock()
    setScrollMode('manual')
  }

  function reset() {
    runIdCounter++
    teardownClock()
    teardownDimTimer()
    storeReset()
    navigate('/')
  }

  function scheduleDim() {
    teardownDimTimer()
    dimTimer = setTimeout(() => {
      dimTimer = null
      // Fade back to the bare-♪ idle look. Preferences (showLyrics, provider,
      // scrobbleEnabled) are untouched — only session state clears.
      storeReset()
      navigate('/')
    }, DIM_TIMEOUT_MS)
  }

  const pipeline: Pipeline = { runRecognition, resyncLyrics, pauseLyrics, reset }
  shared = pipeline
  return pipeline
}

function startClock() {
  teardownClock()
  const snap = getAppSnapshot()
  if (!snap.track || snap.lyrics?.kind !== 'synced') return
  stopClock = startLyricsClock({
    synced: snap.lyrics.lines,
    timecodeMs: snap.track.timecodeMs,
    recognizedAt: snap.track.recognizedAt,
    onTick: (idx) => {
      const current = getAppSnapshot()
      if (current.lyrics?.kind !== 'synced') return
      if (current.lyrics.scrollMode !== 'auto') return
      setLyricIndex(idx)
    },
  })
}

function teardownClock() {
  if (stopClock) {
    stopClock()
    stopClock = null
  }
}

function teardownDimTimer() {
  if (dimTimer !== null) {
    clearTimeout(dimTimer)
    dimTimer = null
  }
}

async function scrobbleRecognition(track: Track): Promise<void> {
  const config = loadLastfmConfig()
  const session = loadSession()
  if (!config || !session) return
  // Anchor the scrobble timestamp to the actual clip-start moment, not to
  // when this fire-and-forget runs. `track.recognizedAt` is a performance.now()
  // value; convert to wall-clock by subtracting how long ago that was.
  const epochAtClipStartMs = Date.now() - (performance.now() - track.recognizedAt)
  const songStartEpochSec = Math.floor((epochAtClipStartMs - track.timecodeMs) / 1000)
  try {
    await scrobble(config, session, {
      artist: track.artist,
      track: track.title,
      album: track.album,
      durationSeconds: track.durationMs ? Math.round(track.durationMs / 1000) : undefined,
      timestampSeconds: songStartEpochSec,
    })
  } catch (err) {
    console.warn('[lastfm] scrobble failed:', err)
  }
}
