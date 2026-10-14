/**
 * SRT parsing.
 *
 * The player reuses the existing timed-line clock, which walks a sorted
 * `[timeMs, text]` timeline and reports the active index. Cue end times are
 * expressed as blank entries so a gap between cues clears the display without
 * any extra timing logic.
 */

export interface Cue {
  startMs: number
  endMs: number
  text: string
}

/** A cue start, or a blank entry marking the end of a cue. */
export type Timeline = [number, string][]

const TIMECODE = /(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})/

/**
 * Parse SRT text into cues, sorted by start time.
 *
 * Tolerates CRLF, a UTF-8 BOM, missing or non-sequential index lines, `.`
 * instead of `,` as the millisecond separator, and blank-line padding. Blocks
 * without a parsable timecode are skipped rather than failing the import.
 */
export function parseSrt(raw: string): Cue[] {
  const text = raw.replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n')
  const cues: Cue[] = []

  for (const block of text.split(/\n[ \t]*\n/)) {
    const lines = block.split('\n')
    const tcIndex = lines.findIndex((l) => TIMECODE.test(l))
    if (tcIndex === -1) continue

    const m = TIMECODE.exec(lines[tcIndex])
    if (!m || [m[2], m[3], m[6], m[7]].some((part) => Number(part) >= 60)) continue

    const body = lines
      .slice(tcIndex + 1)
      .map((l) => stripTags(l).trim())
      .filter(Boolean)
      .join(' ')
    if (!body) continue

    const startMs = toMs(m[1], m[2], m[3], m[4])
    const endMs = toMs(m[5], m[6], m[7], m[8])
    if (endMs > startMs) cues.push({ startMs, endMs, text: body })
  }

  return cues.sort((a, b) => a.startMs - b.startMs)
}

/** Flatten active cues into sorted display intervals, preserving nested overlaps. */
export function toTimeline(cues: Cue[]): Timeline {
  const events = cues.flatMap((cue, index) => cue.endMs <= cue.startMs ? [] : [
    { at: cue.startMs, index, start: true }, { at: cue.endMs, index, start: false },
  ]).sort((a, b) => a.at - b.at || Number(a.start) - Number(b.start))
  const active = new Map<number, string>()
  const timeline: Timeline = []
  for (let i = 0; i < events.length;) {
    const at = events[i].at
    do {
      const event = events[i++]
      if (event.start) active.set(event.index, cues[event.index].text)
      else active.delete(event.index)
    } while (i < events.length && events[i].at === at)
    const text = [...active.values()].join(' ')
    if (!timeline.length || timeline[timeline.length - 1][1] !== text) timeline.push([at, text])
  }
  return timeline
}

/** Latest cue end, including long cues containing shorter overlaps. */
export function durationMs(cues: Cue[]): number {
  return cues.reduce((end, cue) => Math.max(end, cue.endMs), 0)
}

function toMs(h: string, m: string, s: string, frac: string): number {
  const ms = Number(frac.padEnd(3, '0'))
  return Number(h) * 3_600_000 + Number(m) * 60_000 + Number(s) * 1000 + ms
}

/** Remove the SRT/VTT markup the glasses font cannot render anyway. */
function stripTags(line: string): string {
  return line.replace(/<[^>]*>/g, '').replace(/\{\\[^}]*\}/g, '')
}
