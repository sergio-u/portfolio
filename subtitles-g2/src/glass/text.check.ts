/** Pure display checks; no SDK or connected glasses required. */
import assert from 'node:assert/strict'
import { getTextWidth } from '@evenrealities/pretext'
import { INNER_PX, MAX_ROWS, renderCueRows, wrapRows } from './text.ts'
import type { Timeline } from '../state/srt.ts'

const timeline: Timeline = [[0, 'alpha'], [1000, 'bravo'], [2000, 'charlie'], [3000, '']]
assert.equal(renderCueRows(timeline, 1), '\nalpha\nbravo')
assert.equal(renderCueRows(timeline, 2), '\nbravo\ncharlie', 'pairs advance one cue, not two')
assert.equal(renderCueRows(timeline, -1), '')
assert.equal(renderCueRows(timeline, 3), '', 'long silence clears history too')
for (const text of ['supercalifragilisticexpialidocious'.repeat(8), '\u4eca\u5929\u5929\u6c14\u5f88\u597d'.repeat(20)]) {
  const rows = wrapRows(text)
  assert.equal(rows.join(''), text, 'hard wrapping does not drop oversized words or CJK text')
  assert.ok(rows.every((row) => getTextWidth(row) <= INNER_PX))
}
const long = 'This current cue needs several words to fill two visible rows on the glasses display.'
const rendered = renderCueRows([[0, 'history'], [1000, long]], 1)
assert.equal(rendered.split('\n').length, MAX_ROWS)
assert.ok(rendered.includes('history'), 'a two-row current cue retains history')
console.log('text.check.ts: all assertions passed')
