import { startCueClock } from './clock'
import { getAppSnapshot, setAutoSync, setCurrentIndex, setOffsetMs, setTransport, subscribe } from './store'

const DISPLAY_HOLD_MS = 2500
const DISPLAY_DELAY_MS = 500

/** Current unbiased playback position in subtitle time. */
export function positionMs(): number { return positionAt(performance.now()) }

/** Playback position at a monotonic wall-clock reading, excluding display offsets. */
export function positionAt(wallMs: number): number {
  const snap = getAppSnapshot()
  return snap.positionMs + (snap.anchorAt === null ? 0 : (wallMs - snap.anchorAt) * snap.rateFactor)
}

/** Alignment time; manual offsets and the late-display bias must not feed back into sync. */
export function cueTimeAt(wallMs: number): number { return positionAt(wallMs) }

/** Re-anchor by a measured subtitle-time error without changing playback rate. */
export function applyCorrection(lagMs: number): void {
  const snap = getAppSnapshot()
  if (!snap.film || !Number.isFinite(lagMs)) return
  const now = performance.now()
  setTransport({ mode: snap.mode, positionMs: positionAt(now) + lagMs,
    anchorAt: snap.mode === 'playing' ? now : null })
}

/** Anchor an unbiased subtitle time to its original audio timestamp, not response arrival. */
export function lockTo(cueTimeMs: number, atWallMs: number): void {
  if (!getAppSnapshot().film || !Number.isFinite(cueTimeMs) || !Number.isFinite(atWallMs)) return
  setTransport({ mode: 'playing', positionMs: cueTimeMs, anchorAt: atWallMs })
}

/** Start or resume playback from the current position. */
export function play(): void {
  const snap = getAppSnapshot()
  if (!snap.film || snap.mode === 'playing') return
  setTransport({ mode: 'playing', positionMs: snap.positionMs, anchorAt: performance.now() })
}

/** Freeze playback at its current position. */
export function pause(): void {
  const snap = getAppSnapshot()
  if (snap.mode !== 'playing') return
  setTransport({ mode: 'paused', positionMs: positionMs(), anchorAt: null })
}

/** Toggle manual playback. */
export function toggle(): void { getAppSnapshot().mode === 'playing' ? pause() : play() }

/** Seek in subtitle milliseconds while keeping playback or pause state. */
export function seekTo(ms: number): void {
  const snap = getAppSnapshot()
  if (!snap.film || !Number.isFinite(ms)) return
  const playing = snap.mode === 'playing'
  setTransport({ mode: playing ? 'playing' : 'paused',
    positionMs: Math.max(0, Math.min(snap.film.durationMs, ms)), anchorAt: playing ? performance.now() : null })
}

/** Positive adjustments delay display without changing the synchronization clock. */
export function nudgeOffset(deltaMs: number): void { setOffsetMs(getAppSnapshot().offsetMs + deltaMs) }

/** Cancel automatic sync and reset playback to the beginning. */
export function stop(): void {
  setAutoSync(false)
  setTransport({ mode: getAppSnapshot().film ? 'ready' : 'empty', positionMs: 0, anchorAt: null })
  setCurrentIndex(-1)
}

// Own the display timer centrally, including direct film replacement and rate changes.
let stopClock: (() => void) | undefined
let previous = getAppSnapshot()
subscribe(() => {
  const snap = getAppSnapshot()
  const changed = snap.film !== previous.film || snap.mode !== previous.mode ||
    snap.positionMs !== previous.positionMs || snap.anchorAt !== previous.anchorAt ||
    snap.rateFactor !== previous.rateFactor || snap.offsetMs !== previous.offsetMs
  previous = snap
  if (!changed) return
  stopClock?.()
  stopClock = undefined
  if (snap.mode !== 'playing' || !snap.film || snap.anchorAt === null) { setCurrentIndex(-1); return }
  stopClock = startCueClock({ timeline: snap.film.timeline,
    positionMs: snap.positionMs - (snap.offsetMs + DISPLAY_DELAY_MS) * snap.rateFactor,
    anchorAt: snap.anchorAt, rate: snap.rateFactor, holdMs: DISPLAY_HOLD_MS, onTick: setCurrentIndex })
})
