import {
  CreateStartUpPageContainer,
  TextContainerProperty,
  TextContainerUpgrade,
} from '@evenrealities/even_hub_sdk'
import { pxTruncate } from '@evenrealities/pretext'
import type { AppSnapshot } from './shared'

// Container layout is FIXED — two text slots. Mode changes only update text
// content via textContainerUpgrade (flicker-free). No rebuilds.
export const CONTAINER_IDS = {
  header: 0,
  body: 1,
} as const

// Rough inner-pixel widths after padding/border — we use pxTruncate so proportional
// glyphs stay within the text container's inner content box.
const HEADER_INNER_PX = 540
const BODY_INNER_PX = 540

function cleanForG2(text: string): string {
  // Strip emoji/surrogate pairs and other codepoints outside the firmware font range.
  // The firmware replacement glyph varies by build; avoid it by normalizing first.
  // Music symbol block (U+2660-U+266F: card suits and music notes) is preserved
  // for the "♪ Title — Artist" header — assumed but not yet verified to render
  // on the G2 firmware font.
  return text
    .normalize('NFC')
    .replace(/[\u{1F000}-\u{1FFFF}]/gu, '')
    .replace(/[\u{2600}-\u{265F}]/gu, '')
    .replace(/[\u{2670}-\u{27BF}]/gu, '')
}

function fit(text: string, maxPx: number): string {
  return pxTruncate(cleanForG2(text), maxPx)
}

export function initialPage(initial: AppSnapshot): CreateStartUpPageContainer {
  return new CreateStartUpPageContainer({
    containerTotalNum: 2,
    textObject: [
      new TextContainerProperty({
        xPosition: 4,
        yPosition: 8,
        width: 568,
        height: 132,
        paddingLength: 8,
        borderWidth: 0,
        containerID: CONTAINER_IDS.header,
        containerName: 'header',
        content: renderHeader(initial),
        isEventCapture: 0,
      }),
      new TextContainerProperty({
        xPosition: 4,
        yPosition: 148,
        width: 568,
        height: 136,
        paddingLength: 8,
        borderWidth: 0,
        containerID: CONTAINER_IDS.body,
        containerName: 'body',
        content: renderBody(initial),
        isEventCapture: 1,
      }),
    ],
  })
}

export function headerUpgrade(snap: AppSnapshot): TextContainerUpgrade {
  return new TextContainerUpgrade({
    containerID: CONTAINER_IDS.header,
    containerName: 'header',
    content: renderHeader(snap),
  })
}

export function bodyUpgrade(snap: AppSnapshot): TextContainerUpgrade {
  return new TextContainerUpgrade({
    containerID: CONTAINER_IDS.body,
    containerName: 'body',
    content: renderBody(snap),
  })
}

export function renderHeader(snap: AppSnapshot): string {
  if (snap.track) {
    return fit(`♪ ${snap.track.title} — ${snap.track.artist}`, HEADER_INNER_PX)
  }
  switch (snap.mode) {
    case 'listening':
      return '♪ Listening...'
    case 'recognizing':
    case 'fetching-lyrics':
      return '♪ Searching...'
    case 'no-match':
      return '♪ No match'
    case 'error':
      return '♪ Error'
    default:
      return '♪'
  }
}

export function renderBody(snap: AppSnapshot): string {
  if (!snap.track || !snap.showLyrics || !snap.lyrics) return ''
  const lyrics = snap.lyrics
  const items = lyrics.kind === 'synced' ? lyrics.lines.map(([, t]) => t) : lyrics.lines
  const i = lyrics.currentIndex
  return [items[i], items[i + 1]]
    .filter((line): line is string => Boolean(line))
    .map((line) => fit(line, BODY_INNER_PX))
    .join('\n')
}
