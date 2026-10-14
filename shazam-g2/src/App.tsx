import { useEffect, useState, useSyncExternalStore } from 'react'
import { Routes, Route } from 'react-router'
import { AppShell, NavHeader, ScreenHeader, Card, Button, SectionHeader, ListItem } from 'even-toolkit/web'
import { AppGlasses } from './glass/AppGlasses'
import { SIDECAR_URL_KEY, getAppSnapshot, setAudioSource, setProvider, setScrobbleEnabled, setShowLyrics, setSidecarUrl, subscribe } from './state/store'
import { hydrateFromBridge } from './state/persistentStorage'
import { getPipeline } from './state/pipeline'
import {
  LASTFM_SESSION_CHANGED_EVENT,
  LASTFM_SESSION_STORAGE_KEY,
  buildAuthUrl,
  clearPendingAuth,
  clearSession,
  fetchSession,
  getAuthToken,
  loadLastfmConfig,
  loadPendingAuth,
  loadSession,
  savePendingAuth,
  saveSession,
  type LastfmSession,
} from './state/lastfm'
import * as acrcloud from './state/acrcloud'
import type { AppSnapshot, AudioSource } from './glass/shared'

const PROVIDER_LABEL = { audd: 'AudD', acrcloud: 'ACRCloud' } as const
const AUDIO_SOURCE_LABEL = { glasses: 'Glasses', phone: 'Phone', sidecar: 'Sidecar' } as const
const AUDIO_SOURCE_CYCLE: AudioSource[] = ['glasses', 'phone', 'sidecar']

function nextAudioSource(current: AudioSource): AudioSource {
  const i = AUDIO_SOURCE_CYCLE.indexOf(current)
  return AUDIO_SOURCE_CYCLE[(i + 1) % AUDIO_SOURCE_CYCLE.length]
}

const MODE_LABEL: Record<AppSnapshot['mode'], string> = {
  idle: 'Idle',
  listening: 'Listening…',
  recognizing: 'Recognizing…',
  'fetching-lyrics': 'Fetching lyrics…',
  'playing-synced': 'Synced lyrics',
  'playing-plain': 'Plain lyrics',
  'metadata-only': 'Metadata only',
  'no-match': 'No match',
  error: 'Error',
}

function useAppSnapshot(): AppSnapshot {
  return useSyncExternalStore(subscribe, getAppSnapshot, getAppSnapshot)
}

function Home() {
  const snap = useAppSnapshot()
  const tokenSet = Boolean(import.meta.env.VITE_AUDD_TOKEN)
  const acrcloudConfigured = acrcloud.isConfigured()

  useEffect(() => {
    // Pull host-stored values for keys whose localStorage cache is empty
    // (typical after a packaged-.ehpk restart). Sidecar URL goes through the
    // store; Last.fm session re-reads via the session-changed event so the
    // LastfmSettings component picks it up.
    void hydrateFromBridge([SIDECAR_URL_KEY, LASTFM_SESSION_STORAGE_KEY], (key, value) => {
      if (key === SIDECAR_URL_KEY) {
        setSidecarUrl(value)
      } else if (key === LASTFM_SESSION_STORAGE_KEY) {
        window.dispatchEvent(new CustomEvent(LASTFM_SESSION_CHANGED_EVENT))
      }
    })
  }, [])

  const handleRecognize = () => getPipeline()?.runRecognition()
  const handleReset = () => getPipeline()?.reset()
  const handlePauseResume = () => {
    const p = getPipeline()
    if (!p) return
    if (snap.lyrics?.kind === 'synced' && snap.lyrics.scrollMode === 'auto') p.pauseLyrics()
    else p.resyncLyrics()
  }
  const syncToggleLabel =
    snap.lyrics?.kind === 'synced' && snap.lyrics.scrollMode === 'auto' ? 'Pause sync' : 'Resume sync'
  const canToggleSync = snap.lyrics?.kind === 'synced'

  return (
    <AppShell header={<NavHeader title="Shazam G2" />}>
      <div className="px-3 pt-4 pb-8 space-y-3">
        <ScreenHeader title={MODE_LABEL[snap.mode]} subtitle={snap.error ?? statusSubtitle(snap)} />

        {snap.track ? <TrackCard snap={snap} /> : <IdleCard tokenSet={tokenSet} snap={snap} />}

        <SectionHeader title="Controls" />
        <div className="flex gap-2 flex-wrap">
          <Button
            variant="highlight"
            size="sm"
            onClick={handleRecognize}
            disabled={snap.mode === 'listening' || snap.mode === 'recognizing'}
          >
            {snap.mode === 'idle' ? 'Recognize' : 'Recognize again'}
          </Button>
          {canToggleSync && (
            <Button variant="ghost" size="sm" onClick={handlePauseResume}>
              {syncToggleLabel}
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={() => setShowLyrics(!snap.showLyrics)}>
            Lyrics: {snap.showLyrics ? 'On' : 'Off'}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setProvider(snap.provider === 'audd' ? 'acrcloud' : 'audd')}
          >
            Provider: {PROVIDER_LABEL[snap.provider]}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setAudioSource(nextAudioSource(snap.audioSource))}
          >
            Mic: {AUDIO_SOURCE_LABEL[snap.audioSource]}
          </Button>
          <Button variant="ghost" size="sm" onClick={handleReset}>
            Reset
          </Button>
        </div>

        {snap.audioSource === 'sidecar' && <SidecarUrlInput value={snap.sidecarUrl} />}

        {!tokenSet && snap.provider === 'audd' && (
          <Card>
            <div className="p-3 text-sm">
              <strong>No AudD token.</strong> Create <code>.env.local</code> with
              <code> VITE_AUDD_TOKEN=your-token</code>, then restart <code>npm run dev</code>.
              AudD also allows ~300 anonymous requests if you leave the token blank.
            </div>
          </Card>
        )}

        {!acrcloudConfigured && snap.provider === 'acrcloud' && (
          <Card>
            <div className="p-3 text-sm">
              <strong>ACRCloud not configured.</strong> Set <code>VITE_ACRCLOUD_HOST</code>,{' '}
              <code>VITE_ACRCLOUD_ACCESS_KEY</code>, and <code>VITE_ACRCLOUD_ACCESS_SECRET</code> in{' '}
              <code>.env.local</code>, then restart <code>npm run dev</code>.
            </div>
          </Card>
        )}

        <SectionHeader title="Last.fm" />
        <LastfmSettings />
      </div>
      <AppGlasses />
    </AppShell>
  )
}

function statusSubtitle(snap: AppSnapshot): string {
  if (snap.mode === 'idle') return 'Tap Recognize (or tap the glasses) to identify a song'
  if (snap.mode === 'listening') return 'Recording 10 seconds of audio…'
  if (snap.mode === 'recognizing') return 'Sending clip to AudD'
  if (snap.mode === 'fetching-lyrics') return 'Looking up lyrics on LRCLIB'
  if (snap.lyrics?.kind === 'synced' && snap.lyrics.scrollMode === 'manual') return 'Manual scroll — tap to resync'
  return ''
}

function TrackCard({ snap }: { snap: AppSnapshot }) {
  const track = snap.track!
  const lyrics = snap.lyrics
  const currentLine =
    snap.showLyrics && lyrics?.kind === 'synced'
      ? lyrics.lines[lyrics.currentIndex]?.[1]
      : snap.showLyrics && lyrics?.kind === 'plain'
        ? lyrics.lines[lyrics.currentIndex]
        : null

  return (
    <Card>
      <div className="p-3">
        <div className="min-w-0">
          <div className="text-base font-semibold truncate">{track.title}</div>
          <div className="text-sm opacity-70 truncate">{track.artist}</div>
          {track.album && <div className="text-xs opacity-50 truncate">{track.album}</div>}
        </div>
      </div>
      {currentLine !== null && currentLine !== undefined && (
        <div className="px-3 pb-3">
          <div className="text-xs opacity-50 uppercase tracking-wide mb-1">
            {lyrics?.kind === 'synced' ? 'Now singing' : 'Lyrics'}
          </div>
          <div className="text-sm">{currentLine || '♪'}</div>
        </div>
      )}
    </Card>
  )
}

function IdleCard({ tokenSet, snap }: { tokenSet: boolean; snap: AppSnapshot }) {
  return (
    <Card>
      <ListItem title="How it works" subtitle="Tap the glasses touchbar to start a 10s recording" />
      <ListItem
        title="Sources"
        subtitle={`${PROVIDER_LABEL[snap.provider]} for recognition, LRCLIB for synced lyrics, lyrics.ovh as fallback`}
      />
      <ListItem
        title="Token"
        subtitle={tokenSet ? 'Loaded from .env.local' : 'Running without a token (300 trial requests)'}
      />
    </Card>
  )
}

function SidecarUrlInput({ value }: { value: string }) {
  const [draft, setDraft] = useState(value)
  return (
    <div className="flex items-center gap-2 text-sm">
      <label htmlFor="sidecar-url" className="opacity-70 shrink-0">Sidecar URL:</label>
      <input
        id="sidecar-url"
        type="text"
        placeholder="ws://192.168.1.42:5174"
        value={draft}
        onChange={(e) => setDraft(e.currentTarget.value)}
        onBlur={() => setSidecarUrl(draft.trim())}
        onKeyDown={(e) => {
          if (e.key === 'Enter') (e.currentTarget as HTMLInputElement).blur()
        }}
        className="flex-1 bg-transparent border-b border-current/30 outline-none px-1"
      />
    </div>
  )
}

function LastfmSettings() {
  const snap = useAppSnapshot()
  const config = loadLastfmConfig()
  const [session, setSession] = useState<LastfmSession | null>(() => loadSession())
  const [pending, setPending] = useState<{ token: string; authUrl: string } | null>(() => loadPendingAuth())
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    // The session itself is mutated by saveSession/clearSession (which
    // dispatch this event) and by hydrateFromBridge after a .ehpk restart.
    const handler = () => setSession(loadSession())
    window.addEventListener(LASTFM_SESSION_CHANGED_EVENT, handler)
    return () => window.removeEventListener(LASTFM_SESSION_CHANGED_EVENT, handler)
  }, [])

  if (!config) {
    return (
      <Card>
        <div className="p-3 text-sm">
          <strong>No Last.fm credentials.</strong> Set <code>VITE_LASTFM_API_KEY</code> and{' '}
          <code>VITE_LASTFM_SHARED_SECRET</code> in <code>.env.local</code>, then restart{' '}
          <code>npm run dev</code>.
        </div>
      </Card>
    )
  }

  if (session) {
    return (
      <Card>
        <ListItem
          title={`Connected as @${session.username}`}
          subtitle={
            snap.scrobbleEnabled
              ? 'Recognized songs are scrobbled to Last.fm'
              : 'Scrobbling is paused — recognized songs are not sent to Last.fm'
          }
        />
        <div className="px-3 pb-3 flex gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setScrobbleEnabled(!snap.scrobbleEnabled)}
          >
            Scrobble: {snap.scrobbleEnabled ? 'On' : 'Off'}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              clearSession()
              setSession(null)
            }}
          >
            Disconnect
          </Button>
        </div>
      </Card>
    )
  }

  const startConnect = async () => {
    setError(null)
    setBusy(true)
    try {
      const token = await getAuthToken(config)
      const next = { token, authUrl: buildAuthUrl(config, token) }
      savePendingAuth(next)
      setPending(next)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start Last.fm auth')
    } finally {
      setBusy(false)
    }
  }

  const finishConnect = async () => {
    if (!pending) return
    setError(null)
    setBusy(true)
    try {
      const next = await fetchSession(config, pending.token)
      saveSession(next)
      setSession(next)
      clearPendingAuth()
      setPending(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authorization not complete — try again')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <ListItem title="Not connected" subtitle="Scrobble recognized songs to your Last.fm profile" />
      <div className="px-3 pb-3 flex flex-col gap-2">
        {!pending ? (
          <div>
            <Button variant="highlight" size="sm" onClick={startConnect} disabled={busy}>
              {busy ? 'Starting…' : 'Connect Last.fm'}
            </Button>
          </div>
        ) : (
          <>
            <a
              href={pending.authUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm underline"
            >
              1. Open Last.fm to authorize this app
            </a>
            <div className="flex gap-2">
              <Button variant="highlight" size="sm" onClick={finishConnect} disabled={busy}>
                {busy ? 'Finishing…' : "2. I've authorized"}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  clearPendingAuth()
                  setPending(null)
                  setError(null)
                }}
                disabled={busy}
              >
                Cancel
              </Button>
            </div>
          </>
        )}
        {error && <div className="text-xs text-red-600">{error}</div>}
      </div>
    </Card>
  )
}

export function App() {
  return (
    <Routes>
      <Route path="/*" element={<Home />} />
    </Routes>
  )
}
