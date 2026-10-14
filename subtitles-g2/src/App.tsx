import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { Routes, Route } from 'react-router'
import { AppGlasses } from './glass/AppGlasses'
import { renderText } from './glass/layouts'
import { SyncSettings } from './SyncSettings'
import { ASR_URL_KEY, SIDECAR_URL_KEY, getAppSnapshot, setAsrUrl, setAudioSource, setError, setFilm, setMicLatencyMs, setRateFactor, setSidecarUrl, subscribe } from './state/store'
import { hydrateFromBridge } from './state/persistentStorage'
import { nudgeOffset, pause, play, positionMs, seekTo, stop } from './state/player'
import { startAutoSync, stopAutoSync, findMyPlace, syncNow } from './state/autosync'
import { listBundled } from './state/bundled'
import { durationMs, parseSrt, toTimeline } from './state/srt'
import type { AppSnapshot, AudioSource } from './glass/shared'

const AUDIO_SOURCE_LABEL = { glasses: 'Glasses', phone: 'Phone', sidecar: 'Sidecar' } as const
const AUDIO_SOURCES: AudioSource[] = ['glasses', 'phone', 'sidecar']
const NUDGE_STEP_MS = 500
const LATENCY_STEP_MS = 50

const MODE_LABEL: Record<AppSnapshot['mode'], string> = {
  empty: 'No subtitles loaded',
  ready: 'Ready',
  searching: 'Listening for the film',
  playing: 'Playing',
  paused: 'Paused',
}

function useAppSnapshot(): AppSnapshot {
  return useSyncExternalStore(subscribe, getAppSnapshot, getAppSnapshot)
}

function Button({
  onClick,
  children,
  primary = false,
  disabled = false,
}: {
  onClick: () => void
  children: React.ReactNode
  primary?: boolean
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={[
        'rounded-[6px] px-3 py-1.5 text-sm border transition-colors disabled:opacity-40',
        primary
          ? 'border-transparent bg-accent text-bg font-medium'
          : 'border-border text-text hover:border-accent',
      ].join(' ')}
    >
      {children}
    </button>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3 py-1.5 text-sm">
      <span className="text-text-dim shrink-0">{label}</span>
      <span className="text-right whitespace-pre-line">{value}</span>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-xs uppercase tracking-wide text-text-dim">{title}</h2>
      {children}
    </section>
  )
}

/** Load subtitle text into the store, reporting a parse that yielded nothing. */
function loadSubtitles(name: string, raw: string) {
  if (raw.length > 5_000_000) { setError('Subtitle text is too large (5 MB maximum)'); return }
  const cues = parseSrt(raw)
  if (cues.length === 0) {
    setError('No cues found — is this an SRT file?')
    return
  }
  setFilm({ name, cues, timeline: toTimeline(cues), durationMs: durationMs(cues) })
}

function Home() {
  const snap = useAppSnapshot()
  const bundled = listBundled()
  const autoLoaded = useRef(false)

  useEffect(() => {
    // Pull host-stored values for keys whose localStorage cache is empty
    // (typical after a packaged-.ehpk restart).
    void hydrateFromBridge([SIDECAR_URL_KEY, ASR_URL_KEY], (key, value) => {
      if (key === SIDECAR_URL_KEY) setSidecarUrl(value)
      if (key === ASR_URL_KEY) setAsrUrl(value)
    })
  }, [])

  useEffect(() => {
    // One bundled film and nothing loaded: start from it, so arriving at the
    // cinema needs no import step. Only once, so choosing different subtitles
    // is not immediately undone.
    if (autoLoaded.current || snap.film || bundled.length !== 1) return
    autoLoaded.current = true
    loadSubtitles(bundled[0].name, bundled[0].text)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snap.film])

  return (
    <div className="px-4 pt-5 pb-10 space-y-5">
      <header>
        <h1 className="text-lg font-semibold">Subtitles G2</h1>
        <p className="text-sm text-text-dim">
          {snap.error ?? (snap.film ? `${MODE_LABEL[snap.mode]} · ${snap.film.cues.length} cues` : 'Import an SRT file to begin')}
        </p>
      </header>

      {snap.film ? <FilmPanel snap={snap} /> : <ImportPanel bundled={bundled} />}

      {snap.film && (
        <Section title="Transport">
          <div className="flex gap-2 flex-wrap">
            <Button primary onClick={() => (snap.mode === 'playing' ? pause() : play())}>
              {snap.mode === 'playing' ? 'Pause' : 'Play'}
            </Button>
            <Button onClick={() => stop()}>Restart</Button>
            <Button onClick={() => nudgeOffset(NUDGE_STEP_MS)}>Later +0.5s</Button>
            <Button onClick={() => nudgeOffset(-NUDGE_STEP_MS)}>Earlier -0.5s</Button>
            <Button onClick={() => nudgeOffset(-snap.offsetMs)}>Reset offset</Button>
            <Button onClick={() => setFilm(null)}>Change subtitles</Button>
          </div>
          <SeekRow snap={snap} />
          <label className="flex gap-2 items-center text-sm">
            Subtitle speed
            <select value={snap.rateFactor} onChange={(event) => setRateFactor(Number(event.target.value))}
              className="bg-surface border border-border rounded px-2 py-1">
              <option value={1}>1x (matching release)</option>
              <option value={25 / 24}>25 / 24</option>
              <option value={24 / 25}>24 / 25</option>
              <option value={25 / 23.976}>25 / 23.976</option>
              <option value={23.976 / 25}>23.976 / 25</option>
              <option value={24 / 23.976}>24 / 23.976</option>
              <option value={23.976 / 24}>23.976 / 24</option>
            </select>
          </label>
        </Section>
      )}

      {snap.film && (
        <Section title="Sync">
          <SyncSettings snap={snap} />
          <div className="flex gap-2 flex-wrap">
            <Button primary disabled={snap.syncBusy} onClick={() => void findMyPlace()}>Find my place</Button>
            <Button disabled={snap.syncBusy || snap.mode !== 'playing'} onClick={() => void syncNow()}>Re-sync now</Button>
            {snap.syncBusy && <Button onClick={() => stopAutoSync()}>Cancel listening</Button>}
            <Button
              onClick={() => {
                snap.autoSync ? stopAutoSync() : startAutoSync()
              }}
            >
              Automatic: {snap.autoSync ? 'On' : 'Off'}
            </Button>
          </div>
          <p className="text-sm text-text-dim">
            {snap.syncStatus ?? 'Listens to the room and finds where the film is. No need to start it on time.'}
            {snap.autoSync && snap.syncCadenceMs !== null && ` · checking every ${Math.round(snap.syncCadenceMs / 60_000)} min`}
          </p>
        </Section>
      )}

      <Section title="Microphone">
        <div className="flex gap-2 flex-wrap">
          {AUDIO_SOURCES.map((source) => (
            <Button key={source} primary={snap.audioSource === source} onClick={() => setAudioSource(source)}>
              {AUDIO_SOURCE_LABEL[source]}
            </Button>
          ))}
        </div>
        <p className="text-sm text-text-dim">
          {snap.audioSource === 'sidecar'
            ? 'Development only: streams from a laptop microphone.'
            : 'Whichever hears the screen better in your seat.'}
        </p>
        {snap.audioSource === 'sidecar' && <SidecarUrlInput value={snap.sidecarUrl} />}

        <div className="flex gap-2 flex-wrap items-center">
          <span className="text-sm text-text-dim">Residual mic delay: {snap.micLatencyMs} ms</span>
          <Button onClick={() => setMicLatencyMs(Math.max(0, snap.micLatencyMs - LATENCY_STEP_MS))}>-50</Button>
          <Button onClick={() => setMicLatencyMs(snap.micLatencyMs + LATENCY_STEP_MS)}>+50</Button>
        </div>
        <p className="text-sm text-text-dim">Microphone/Bluetooth delay only. Network and recognition time are accounted for automatically.</p>
      </Section>
    </div>
  )
}

/** File import plus a paste fallback for WebViews without a file chooser. */
function ImportPanel({ bundled }: { bundled: { name: string; text: string }[] }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [pasted, setPasted] = useState('')

  const handleFiles = async (files: FileList | null) => {
    const file = files?.[0]
    if (!file) return
    try {
      if (file.size > 5_000_000) throw new Error('Subtitle file is too large (5 MB maximum)')
      loadSubtitles(file.name.replace(/\.[^.]+$/, ''), await file.text())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not read that file')
    } finally {
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <div className="rounded-[6px] border border-border bg-surface p-3 space-y-4">
      {bundled.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm text-text-dim">Bundled with this build:</p>
          <div className="flex gap-2 flex-wrap">
            {bundled.map((b) => (
              <Button key={b.name} primary onClick={() => loadSubtitles(b.name, b.text)}>
                {b.name}
              </Button>
            ))}
          </div>
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        // No accept filter: WebView file choosers map .srt to no MIME type and
        // hide it when one is set.
        className="hidden"
        onChange={(e) => void handleFiles(e.target.files)}
      />
      <Button primary={bundled.length === 0} onClick={() => inputRef.current?.click()}>
        Choose SRT file
      </Button>

      <div className="space-y-2">
        <p className="text-sm text-text-dim">Or paste subtitle text:</p>
        <textarea
          value={pasted}
          onChange={(e) => setPasted(e.target.value)}
          rows={4}
          placeholder={'1\n00:00:12,000 --> 00:00:14,500\nFirst line of dialogue'}
          className="w-full rounded-[6px] bg-transparent border border-border p-2 text-sm font-mono"
        />
        <Button disabled={!pasted.trim()} onClick={() => loadSubtitles('Pasted subtitles', pasted)}>
          Load pasted text
        </Button>
      </div>
    </div>
  )
}

function FilmPanel({ snap }: { snap: AppSnapshot }) {
  const film = snap.film
  if (!film) return null
  const line = renderText(snap)
  return (
    <div className="rounded-[6px] border border-border bg-surface px-3 py-2 divide-y divide-border">
      <Row label={film.name} value={`${film.cues.length} cues · ${formatMs(film.durationMs)}`} />
      <Row label="Sync offset" value={`${snap.offsetMs >= 0 ? '+' : ''}${(snap.offsetMs / 1000).toFixed(1)}s`} />
      {snap.rateFactor !== 1 && <Row label="Drift rate" value={`${((snap.rateFactor - 1) * 100).toFixed(2)}%`} />}
      <Row label="On glasses" value={line || '(silent)'} />
    </div>
  )
}

/** Position readout with coarse scrubbing, for joining a film already in progress. */
function SeekRow({ snap }: { snap: AppSnapshot }) {
  const [, force] = useState(0)

  useEffect(() => {
    if (snap.mode !== 'playing') return
    const handle = window.setInterval(() => force((n) => n + 1), 500)
    return () => window.clearInterval(handle)
  }, [snap.mode])

  const film = snap.film
  if (!film) return null

  return (
    <div className="space-y-1">
      <p className="text-sm text-text-dim">
        {formatMs(positionMs())} / {formatMs(film.durationMs)}
      </p>
      <input
        type="range"
        aria-label="Playback position"
        min={0}
        max={Math.max(film.durationMs, 1)}
        step={1000}
        value={Math.min(positionMs(), film.durationMs)}
        onChange={(e) => seekTo(Number(e.target.value))}
        className="w-full accent-accent"
      />
    </div>
  )
}

function SidecarUrlInput({ value }: { value: string }) {
  const [draft, setDraft] = useState(value)
  useEffect(() => setDraft(value), [value])
  return (
    <div className="flex items-center gap-2 text-sm">
      <label htmlFor="sidecar-url" className="text-text-dim shrink-0">Sidecar URL:</label>
      <input
        id="sidecar-url"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => setSidecarUrl(draft.trim())}
        placeholder="ws://192.168.1.42:5174"
        className="flex-1 rounded-[6px] bg-transparent border border-border px-2 py-1"
      />
    </div>
  )
}

function formatMs(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const mm = String(m).padStart(h > 0 ? 2 : 1, '0')
  return `${h > 0 ? `${h}:` : ''}${mm}:${String(s).padStart(2, '0')}`
}

export function App() {
  return (
    <>
      <AppGlasses />
      <Routes>
        <Route path="/" element={<Home />} />
      </Routes>
    </>
  )
}
