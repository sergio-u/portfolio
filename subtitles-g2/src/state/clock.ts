export interface CueClockConfig {
  /** Sorted `[timeMs, text]` entries; a blank entry clears the display. */
  timeline: [number, string][]
  /** Playback position at the anchor. */
  positionMs: number
  /** performance.now() the position was captured at. */
  anchorAt: number
  /**
   * Cue time advanced per millisecond of wall clock. Values other than 1
   * correct a framerate mismatch between the subtitle release and the screening.
   */
  rate?: number
  /**
   * How long a line stays up after its cue ends.
   *
   * Reading a line a moment after it was spoken is the normal case when
   * subtitles are a backstop for missed dialogue rather than the main channel,
   * so short gaps hold the previous line instead of blanking.
   */
  holdMs?: number
  onTick: (index: number) => void
  intervalMs?: number
}

/** Report the active timeline index as playback advances. Returns a stop function. */
export function startCueClock(cfg: CueClockConfig): () => void {
  const interval = cfg.intervalMs ?? 200
  let lastIndex: number | undefined
  let stopped = false

  function tick() {
    if (stopped) return
    const elapsed = (performance.now() - cfg.anchorAt) * (cfg.rate ?? 1)
    const position = cfg.positionMs + elapsed
    const idx = holdIndex(findActiveIndex(cfg.timeline, position), position, cfg)
    if (idx !== lastIndex) {
      lastIndex = idx
      cfg.onTick(idx)
    }
  }

  tick()
  const handle = window.setInterval(tick, interval)

  return () => {
    stopped = true
    window.clearInterval(handle)
  }
}

/**
 * Keep the previous line up through a short gap.
 *
 * Only affects what is displayed; alignment still works from the true cue
 * timings.
 */
function holdIndex(index: number, positionMs: number, cfg: CueClockConfig): number {
  const hold = cfg.holdMs ?? 0
  if (hold <= 0 || index <= 0) return index

  const entry = cfg.timeline[index]
  if (!entry || entry[1] !== '') return index
  return positionMs - entry[0] < hold ? index - 1 : index
}

function findActiveIndex(timeline: [number, string][], positionMs: number): number {
  if (timeline.length === 0) return -1
  if (positionMs < timeline[0][0]) return -1

  let lo = 0
  let hi = timeline.length - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >>> 1
    if (timeline[mid][0] <= positionMs) lo = mid
    else hi = mid - 1
  }
  return lo
}
