import { HAS_BUNDLED_ASR_KEY, transcribeLive } from './asr'
import { matchTranscript, matchedPositionAt } from './transcript'
import { measureOffline } from './offlineSync'
import { applyCorrection, cueTimeAt, lockTo } from './player'
import { getAppSnapshot, getSyncRevision, setAutoSync, setMode, setRateFactor,
  setSyncBusy, setSyncCadenceMs, setSyncStatus, subscribe } from './store'

const BASE_CYCLE_MS = 300_000
const MAX_CYCLE_MS = 1_200_000
const RETRY_MS = 60_000

/** Outcome of one bounded sync request. */
export interface SyncResult {
  status: string
  appliedMs: number | null
}

type Estimate = { cueTimeMs: number; startedAt: number; rate: number; uncertaintyMs: number }
let active: AbortController | null = null
let timer: number | undefined
let cycleMs = BASE_CYCLE_MS
let confirmationPending = false
let pendingJump: { positionMs: number; at: number; rate: number; revision: number } | null = null

/** Search the whole subtitle track using the selected synchronization method. */
export function findMyPlace(): Promise<SyncResult> { return synchronize(true) }

/** Correct drift near the current clock; playback must already be running. */
export function syncNow(): Promise<SyncResult> { return synchronize(false) }

/** Stop a capture or pending provider response without changing the playback clock. */
export function cancelSync(): void { active?.abort(new DOMException('Listening cancelled', 'AbortError')) }

async function synchronize(acquire: boolean): Promise<SyncResult> {
  if (active) return { status: 'Already listening', appliedMs: null }
  const before = getAppSnapshot()
  if (!before.film) return finish('No subtitles loaded', null)
  if (!acquire && before.mode !== 'playing') return finish('Start playback or use Find my place first', null)
  if (before.syncEngine === 'asr') {
    if (!before.asrConsent) return finish('Cloud sync needs microphone upload consent', null)
    if (!HAS_BUNDLED_ASR_KEY && (!before.asrAccessToken || !before.asrUrl)) {
      return finish('Cloud sync needs a server URL and an access token', null)
    }
  }
  if (acquire && before.mode !== 'playing') setMode('searching')
  const snap = getAppSnapshot()
  const revision = getSyncRevision()
  const controller = new AbortController()
  active = controller
  setSyncBusy(true)
  setSyncStatus(snap.syncEngine === 'asr' ? 'Listening with Soniox...' : 'Listening offline...')
  const unwatch = subscribe(() => {
    if (getSyncRevision() !== revision) controller.abort(new DOMException('Playback or sync settings changed', 'AbortError'))
  })
  try {
    let estimate: Estimate | null = null
    if (snap.syncEngine === 'asr') {
      const recognition = await transcribeLive(acquire ? 25_000 : 20_000, {
        tokenUrl: snap.asrUrl, accessToken: snap.asrAccessToken,
        preferredSource: snap.audioSource, sidecarUrl: snap.sidecarUrl, signal: controller.signal,
      })
      controller.signal.throwIfAborted()
      const expected = acquire ? undefined : cueTimeAt(recognition.startedAt) - snap.micLatencyMs * snap.rateFactor
      let matched = matchTranscript(snap.film!.cues, recognition.words, snap.rateFactor, expected)
      // Search broadly on failure, but a large resulting jump needs an independent capture.
      if (!matched && !acquire) matched = matchTranscript(snap.film!.cues, recognition.words, snap.rateFactor)
      if (matched) estimate = { cueTimeMs: matched.cueTimeMs, startedAt: recognition.startedAt,
        rate: snap.rateFactor, uncertaintyMs: matched.uncertaintyMs }
    } else {
      const measured = await measureOffline(snap, acquire, controller.signal)
      if (measured) estimate = { ...measured, uncertaintyMs: 200 }
    }
    controller.signal.throwIfAborted()
    if (getSyncRevision() !== revision) return { status: 'Playback changed; result discarded', appliedMs: null }
    if (!estimate) return finish('No reliable dialogue match; clock unchanged', null)
    unwatch()
    const now = performance.now()
    // ASR timestamps are relative to audio zero. Extrapolate through capture,
    // uplink, inference, finalization and roundtrip time exactly once.
    const position = matchedPositionAt(estimate.cueTimeMs, estimate.startedAt, now,
      estimate.rate, snap.micLatencyMs)
    const delta = position - cueTimeAt(now)
    if (!acquire && Math.abs(delta) > 5000) {
      const agreed = pendingJump && pendingJump.revision === revision &&
        now - pendingJump.at < 180_000 &&
        Math.abs(position - (pendingJump.positionMs + (now - pendingJump.at) * pendingJump.rate)) < 1500
      if (!agreed) {
        pendingJump = { positionMs: position, at: now, rate: estimate.rate, revision }
        return finish('Large drift found; another matching capture is required', null)
      }
    }
    pendingJump = null
    if (acquire) {
      setRateFactor(estimate.rate)
      lockTo(estimate.cueTimeMs + snap.micLatencyMs * estimate.rate, estimate.startedAt)
      confirmationPending = true
      cycleMs = BASE_CYCLE_MS
      return finish('Position found; next capture will confirm it', null)
    }
    // Prefer a little late to early. SRT boundary uncertainty widens either gate.
    const threshold = Math.max(delta < 0 ? 300 : 1200, 2 * estimate.uncertaintyMs)
    const correction = Math.abs(delta) >= threshold ? delta : 0
    if (correction) applyCorrection(correction)
    confirmationPending = false
    return finish(correction ? `Adjusted ${correction >= 0 ? '+' : ''}${(correction / 1000).toFixed(1)}s` : 'In sync', correction)
  } catch (error) {
    if (controller.signal.aborted) {
      // Do not overwrite the status of a newly selected film or synchronization mode.
      const status = controller.signal.reason instanceof Error ? controller.signal.reason.message : 'Listening cancelled'
      const current = getAppSnapshot()
      return current.film === snap.film && current.syncEngine === snap.syncEngine
        ? finish(status, null) : { status, appliedMs: null }
    }
    return finish(error instanceof Error ? error.message : 'Synchronization failed', null)
  } finally {
    unwatch()
    active = null
    setSyncBusy(false)
    if (getAppSnapshot().autoSync) schedule()
  }
}

/** Enable periodic checks; initial acquisition still requires Find my place. */
export function startAutoSync(): void {
  if (getAppSnapshot().autoSync) return
  cycleMs = BASE_CYCLE_MS
  setAutoSync(true)
}

/** Disable automatic checks and cancel any capture in progress. */
export function stopAutoSync(): void {
  setAutoSync(false)
  cancelSync()
  window.clearTimeout(timer)
  timer = undefined
  setSyncCadenceMs(null)
}

function schedule(): void {
  window.clearTimeout(timer)
  timer = undefined
  if (!getAppSnapshot().autoSync) return
  const wait = confirmationPending || pendingJump || getAppSnapshot().mode === 'searching' ? RETRY_MS : cycleMs
  setSyncCadenceMs(wait)
  timer = window.setTimeout(() => void runCycle(), wait)
}

async function runCycle(): Promise<void> {
  timer = undefined
  const snap = getAppSnapshot()
  if (!snap.autoSync) return
  if (active) { schedule(); return }
  const result = snap.mode === 'playing' ? await syncNow()
    : snap.mode === 'searching' ? await findMyPlace() : null
  if (!getAppSnapshot().autoSync) return
  // Inconclusive audio is not confirmation and must not widen the checking interval.
  if (result?.appliedMs === 0) cycleMs = Math.min(cycleMs * 2, MAX_CYCLE_MS)
  else if (result && result.appliedMs !== null) cycleMs = BASE_CYCLE_MS
  schedule()
}

let wasAutomatic = getAppSnapshot().autoSync
let previousFilm = getAppSnapshot().film
let previousEngine = getAppSnapshot().syncEngine
subscribe(() => {
  const snap = getAppSnapshot()
  if (snap.film !== previousFilm || snap.syncEngine !== previousEngine) {
    previousFilm = snap.film
    previousEngine = snap.syncEngine
    confirmationPending = false
    pendingJump = null
  }
  if (snap.autoSync === wasAutomatic) return
  wasAutomatic = snap.autoSync
  if (snap.autoSync) schedule()
  else {
    cancelSync()
    window.clearTimeout(timer)
    timer = undefined
    setSyncCadenceMs(null)
  }
})

function finish(status: string, appliedMs: number | null): SyncResult {
  setSyncStatus(status)
  return { status, appliedMs }
}
