import type { EvenHubEvent } from '@evenrealities/even_hub_sdk'

export type GlassIntent =
  | { kind: 'select' }
  | { kind: 'scroll-up' }
  | { kind: 'scroll-down' }
  | { kind: 'back' }
  | { kind: 'foreground-enter' }
  | { kind: 'abnormal-exit' }
  | { kind: 'system-exit' }
  | null

// Raw SDK enum values — CLICK_EVENT=0 is omitted by protobuf for zero values,
// so we treat `undefined` identically to 0. See 03-events.md for the canonical table.
const SCROLL_TOP = 1
const SCROLL_BOTTOM = 2
const DOUBLE_CLICK = 3
const FOREGROUND_ENTER = 4
const ABNORMAL_EXIT = 6
const SYSTEM_EXIT = 7

export function mapEvent(event: EvenHubEvent): GlassIntent {
  if (event.textEvent) {
    const t = event.textEvent.eventType ?? 0
    if (t === SCROLL_TOP) return { kind: 'scroll-up' }
    if (t === SCROLL_BOTTOM) return { kind: 'scroll-down' }
    return null
  }
  if (event.sysEvent) {
    const t = event.sysEvent.eventType ?? 0
    if (t === 0) return { kind: 'select' } // CLICK on a text container
    if (t === DOUBLE_CLICK) return { kind: 'back' }
    if (t === FOREGROUND_ENTER) return { kind: 'foreground-enter' }
    if (t === ABNORMAL_EXIT) return { kind: 'abnormal-exit' }
    if (t === SYSTEM_EXIT) return { kind: 'system-exit' }
    return null
  }
  return null
}
