import { getTextWidth, pxTruncate } from '@evenrealities/pretext'
import type { Timeline } from '../state/srt'

export const INNER_PX = 540
export const MAX_ROWS = 3
const CURRENT_ROWS = 2

/** Remove codepoints outside the supported firmware font ranges. */
export function cleanForG2(text: string): string {
  return text.normalize('NFC')
    .replace(/[\u{1F000}-\u{1FFFF}]/gu, '')
    .replace(/[\u{2600}-\u{265F}]/gu, '')
    .replace(/[\u{2670}-\u{27BF}]/gu, '')
}

/** Explicit pixel-width wrapping, including space-free text and oversized words. */
export function wrapRows(text: string): string[] {
  const rows: string[] = []
  let row = ''
  for (const word of cleanForG2(text).split(/\s+/).filter(Boolean)) {
    const candidate = row ? `${row} ${word}` : word
    if (getTextWidth(candidate) <= INNER_PX) { row = candidate; continue }
    if (row) rows.push(row)
    row = ''
    for (const char of word) {
      if (row && getTextWidth(row + char) > INNER_PX) { rows.push(row); row = '' }
      row += char
    }
  }
  if (row) rows.push(row)
  return rows
}

/** Show current text and recent history, bottom-aligned within a fixed three-row window. */
export function renderCueRows(timeline: Timeline, index: number): string {
  const current = timeline[index]?.[1]
  if (!current) return ''
  const wrapped = wrapRows(current)
  const rows = wrapped.slice(0, CURRENT_ROWS)
  if (wrapped.length > CURRENT_ROWS) {
    rows[CURRENT_ROWS - 1] = pxTruncate(rows[CURRENT_ROWS - 1], INNER_PX - getTextWidth('...')) + '...'
  }
  for (let i = index - 1; i >= 0; i--) {
    if (!timeline[i][1]) continue
    rows.unshift(...wrapRows(timeline[i][1]).slice(-(MAX_ROWS - rows.length)))
    break
  }
  while (rows.length < MAX_ROWS) rows.unshift('')
  return rows.join('\n')
}
