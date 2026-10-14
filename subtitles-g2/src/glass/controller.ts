import {
  waitForEvenAppBridge,
  type EvenAppBridge,
  StartUpPageCreateResult,
} from '@evenrealities/even_hub_sdk'
import {
  initialPage,
  renderText,
  subtitleUpgrade,
} from './layouts'
import { mapEvent, type GlassIntent } from './events'
import { setGlassReady } from './bridgeState'
import type { AppSnapshot } from './shared'

interface Handlers {
  onIntent(intent: Exclude<GlassIntent, null>): void
  getSnapshot(): AppSnapshot
}

// Scroll events fire spuriously for ~80ms after textContainerUpgrade (03-events.md).
const SCROLL_SUPPRESS_MS = 120

async function withTimeout<T>(p: Promise<T>, ms: number, fallback: T): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([
      p.catch(() => fallback),
      new Promise<T>((resolve) => { timer = setTimeout(() => resolve(fallback), ms) }),
    ])
  } finally { clearTimeout(timer) }
}

export class GlassesController {
  private bridge: EvenAppBridge | null = null
  private unsubscribe: (() => void) | null = null
  private isPageCreated = false
  private creatingPage = false
  private pageEpoch = 0
  private retries = 0
  private retryTimer: number | undefined
  private textBusy = false
  private textPending = false
  private lastText: string | null = null
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
        this.pageEpoch++
        this.isPageCreated = false
        this.lastText = null
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
    this.pageEpoch++
    window.clearTimeout(this.retryTimer)
    setGlassReady(false)
    if (this.unsubscribe) {
      this.unsubscribe()
      this.unsubscribe = null
    }
  }

  notify(): void {
    if (!this.bridge || this.disposed) return
    this.retries = 0
    void this.recreatePageIfNeeded()
  }

  private async ensurePage(): Promise<void> {
    if (!this.bridge || this.isPageCreated || this.creatingPage || this.disposed) return
    this.creatingPage = true
    const snap = this.handlers.getSnapshot()
    const epoch = this.pageEpoch
    try {
      const result = await this.bridge.createStartUpPageContainer(initialPage(snap))
      if (this.disposed || epoch !== this.pageEpoch) return
      if (result === StartUpPageCreateResult.success) {
        this.isPageCreated = true
        this.lastText = renderText(snap)
        setGlassReady(true)
      } else console.error('[glasses] page creation failed:', result)
    } catch {
      setGlassReady(false)
    } finally { this.creatingPage = false }
  }

  private async recreatePageIfNeeded(): Promise<void> {
    await this.ensurePage()
    await this.flush()
  }

  private async flush(): Promise<void> {
    if (!this.bridge || !this.isPageCreated || this.disposed) return
    if (this.textBusy) {
      this.textPending = true
      return
    }
    this.textBusy = true
    this.textPending = false
    try {
      const snap = this.handlers.getSnapshot()
      const next = renderText(snap)
      if (next !== this.lastText) {
        const epoch = this.pageEpoch
        // A wrapper timeout does not cancel native delivery. Keep this request
        // serialized until the SDK settles, then reconcile the newest snapshot.
        const ok = await this.bridge.textContainerUpgrade(subtitleUpgrade(snap)).catch(() => false)
        if (this.disposed || epoch !== this.pageEpoch) return
        this.lastText = ok ? next : null
        if (ok) {
          this.retries = 0
          this.scrollSuppressUntil = performance.now() + SCROLL_SUPPRESS_MS
        } else if (this.retries++ < 3) {
          window.clearTimeout(this.retryTimer)
          this.retryTimer = window.setTimeout(() => void this.flush(), 500 * this.retries)
        }
      }
    } finally {
      this.textBusy = false
      if (this.textPending) void this.flush()
    }
  }
}
