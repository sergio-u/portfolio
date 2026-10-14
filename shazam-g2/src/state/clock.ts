export interface LyricsClockConfig {
  synced: [number, string][]
  timecodeMs: number
  recognizedAt: number
  onTick: (index: number) => void
  intervalMs?: number
}

export function startLyricsClock(cfg: LyricsClockConfig): () => void {
  const interval = cfg.intervalMs ?? 200
  let lastIndex = -1
  let stopped = false

  function tick() {
    if (stopped) return
    const elapsed = performance.now() - cfg.recognizedAt
    const position = cfg.timecodeMs + elapsed
    const idx = findActiveIndex(cfg.synced, position)
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

function findActiveIndex(lines: [number, string][], positionMs: number): number {
  if (lines.length === 0) return -1
  if (positionMs < lines[0][0]) return -1

  let lo = 0
  let hi = lines.length - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >>> 1
    if (lines[mid][0] <= positionMs) lo = mid
    else hi = mid - 1
  }
  return lo
}
