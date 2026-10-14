import {
  waitForEvenAppBridge,
  type EvenAppBridge,
  StartUpPageCreateResult,
} from '@evenrealities/even_hub_sdk'
import {
  bodyUpgrade,
  headerUpgrade,
  initialPage,
  renderBody,
  renderHeader,
} from './layouts'
import { mapEvent, type GlassIntent } from './events'
import { setGlassReady } from './bridgeState'
import type { AppSnapshot } from './shared'

interface Handlers {
  onIntent(intent: Exclude<GlassIntent, null>): void
  getSnapshot(): AppSnapshot
}

const TEXT_UPGRADE_TIMEOUT_MS = 2000
// Scroll events fire spuriously for ~80ms after textContainerUpgrade (03-events.md).
const SCROLL_SUPPRESS_MS = 120

function withTimeout<T>(p: Promise<T>, ms: number, fallback: T): Promise<T> {
  return Promise.race([
    p.catch(() => fallback),
    new Promise<T>((resolve) => setTimeout(() => resolve(fallback), ms)),
  ])
}

export class GlassesController {
  private bridge: EvenAppBridge | null = null
  private unsubscribe: (() => void) | null = null
  private isPageCreated = false
  private textBusy = false
  private textPending = false
  private lastHeader = ''
  private lastBody = ''
  private scrollSuppressUntil = 0
  private disposed = false

  constructor(private readonly handlers: Handlers) {}

  async init(): Promise<void> {
    if (this.bridge) return
    const bridge = await withTimeout(waitForEvenAppBridge(), 3000, null)
    if (!bridge || this.disposed) return
    this.bridge = bridge
    ;(window as unknown as { __evenBridge?: unknown }).__evenBridge = bridge

    this.unsubscribe = bridge.onEvenHubEvent((event) => {
      const intent = mapEvent(event)
      if (!intent) return
      if ((intent.kind === 'scroll-up' || intent.kind === 'scroll-down') && performance.now() < this.scrollSuppressUntil) {
        return
      }
      if (intent.kind === 'foreground-enter') {
        void this.recreatePageIfNeeded()
        return
      }
      if (intent.kind === 'abnormal-exit') {
        this.isPageCreated = false
        setGlassReady(false)
        return
      }
      this.handlers.onIntent(intent)
    })

    await this.ensurePage()
    await this.flush()
  }

  async dispose(): Promise<void> {
    this.disposed = true
    setGlassReady(false)
    if (this.unsubscribe) {
      this.unsubscribe()
      this.unsubscribe = null
    }
  }

  notify(): void {
    if (!this.bridge || !this.isPageCreated) return
    void this.flush()
  }

  private async ensurePage(): Promise<void> {
    if (!this.bridge || this.isPageCreated) return
    const snap = this.handlers.getSnapshot()
    const result = await withTimeout(
      this.bridge.createStartUpPageContainer(initialPage(snap)),
      5000,
      StartUpPageCreateResult.invalid,
    )
    if (result === StartUpPageCreateResult.success || result === StartUpPageCreateResult.invalid) {
      this.isPageCreated = true
      this.lastHeader = renderHeader(snap)
      this.lastBody = renderBody(snap)
      setGlassReady(true)
    } else {
      // oversize / outOfMemory — nothing we can do.
      console.error('[glasses] createStartUpPageContainer failed:', result)
    }
  }

  private async recreatePageIfNeeded(): Promise<void> {
    if (this.isPageCreated) return
    await this.ensurePage()
    await this.flush()
  }

  private async flush(): Promise<void> {
    if (!this.bridge || !this.isPageCreated) return
    if (this.textBusy) {
      this.textPending = true
      return
    }
    this.textBusy = true
    this.textPending = false
    try {
      // Re-read the snapshot at each upgrade decision so the body upgrade
      // doesn't ride a snapshot that's stale relative to whatever happened
      // during the header upgrade's await.
      const snapH = this.handlers.getSnapshot()
      const nextHeader = renderHeader(snapH)
      if (nextHeader !== this.lastHeader) {
        const ok = await withTimeout(this.bridge.textContainerUpgrade(headerUpgrade(snapH)), TEXT_UPGRADE_TIMEOUT_MS, false)
        if (ok) {
          this.lastHeader = nextHeader
          this.scrollSuppressUntil = performance.now() + SCROLL_SUPPRESS_MS
        }
      }

      const snapB = this.handlers.getSnapshot()
      const nextBody = renderBody(snapB)
      if (nextBody !== this.lastBody) {
        const ok = await withTimeout(this.bridge.textContainerUpgrade(bodyUpgrade(snapB)), TEXT_UPGRADE_TIMEOUT_MS, false)
        if (ok) {
          this.lastBody = nextBody
          this.scrollSuppressUntil = performance.now() + SCROLL_SUPPRESS_MS
        }
      }
    } finally {
      this.textBusy = false
      if (this.textPending) void this.flush()
    }
  }
}
