import {
  CreateStartUpPageContainer,
  TextContainerProperty,
  TextContainerUpgrade,
} from '@evenrealities/even_hub_sdk'
import { pxTruncate } from '@evenrealities/pretext'
import { cleanForG2, INNER_PX, MAX_ROWS, renderCueRows } from './text'
import type { AppSnapshot } from './shared'

// Container layout is FIXED — one text slot holding the current line. Mode
// changes only update text content via textContainerUpgrade (flicker-free).
// No rebuilds.
export const CONTAINER_IDS = {
  subtitle: 0,
} as const

// EvenHub's LVGL build renders text at a fixed 27px line height, so the number
// of lines a container can show is its inner height divided by that.
const LINE_HEIGHT_PX = 27
// Reserve one extra row of geometric slack; actual firmware clipping is unverified.
const PADDING_PX = 8
const CONTAINER_HEIGHT_PX = LINE_HEIGHT_PX * (MAX_ROWS + 1) + PADDING_PX * 2

function fit(text: string, maxPx: number): string {
  return pxTruncate(cleanForG2(text), maxPx)
}

export function initialPage(initial: AppSnapshot): CreateStartUpPageContainer {
  return new CreateStartUpPageContainer({
    containerTotalNum: 1,
    textObject: [
      new TextContainerProperty({
        xPosition: 4,
        yPosition: 8,
        width: 568,
        height: CONTAINER_HEIGHT_PX,
        paddingLength: PADDING_PX,
        borderWidth: 0,
        containerID: CONTAINER_IDS.subtitle,
        containerName: 'subtitle',
        content: renderText(initial),
        isEventCapture: 1,
      }),
    ],
  })
}

export function subtitleUpgrade(snap: AppSnapshot): TextContainerUpgrade {
  return new TextContainerUpgrade({
    containerID: CONTAINER_IDS.subtitle,
    containerName: 'subtitle',
    content: renderText(snap),
  })
}

/**
 * The glasses show a rolling window of recent rows while playing.
 *
 * Status only appears when there is no line to show, so the display stays dark
 * during a film instead of advertising state the phone already reports.
 */
export function renderText(snap: AppSnapshot): string {
  if (!snap.film) return 'No subtitles loaded'

  if (snap.mode === 'playing') return renderCueRows(snap.film.timeline, snap.currentIndex)

  switch (snap.mode) {
    case 'searching':
      return 'Listening for the film...'
    case 'paused':
      return fit(`${snap.film.name} (paused)`, INNER_PX)
    default:
      return fit(`${snap.film.name} — tap to start`, INNER_PX)
  }
}
