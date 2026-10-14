const TIMESTAMP_RE = /\[(\d{1,3}):(\d{2})(?:\.(\d{1,3}))?\]/g
const METADATA_RE = /^\[(ar|al|ti|au|length|by|offset|re|ve):/i

export function parseLrc(raw: string): [number, string][] {
  const out: [number, string][] = []
  const lines = raw.split(/\r?\n/)

  for (const rawLine of lines) {
    const trimmed = rawLine.trim()
    if (!trimmed) continue
    if (METADATA_RE.test(trimmed)) continue

    const timestamps: number[] = []
    let lastMatchEnd = 0
    TIMESTAMP_RE.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = TIMESTAMP_RE.exec(trimmed)) !== null) {
      const min = Number(m[1])
      const sec = Number(m[2])
      const fracRaw = m[3] ?? '0'
      const frac = Number(fracRaw.padEnd(3, '0').slice(0, 3))
      timestamps.push(min * 60_000 + sec * 1000 + frac)
      lastMatchEnd = m.index + m[0].length
    }
    if (timestamps.length === 0) continue

    const text = trimmed.slice(lastMatchEnd).trim()
    for (const ts of timestamps) out.push([ts, text])
  }

  out.sort((a, b) => a[0] - b[0])
  return out
}
