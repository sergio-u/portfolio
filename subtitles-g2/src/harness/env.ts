/**
 * Browser globals and a virtual clock, so the app's state modules can run under
 * Node without a browser.
 *
 * Import this module *before* anything that touches `window` or `performance`;
 * static import order guarantees it is evaluated first.
 */

interface ScheduledTask {
  id: number
  dueAt: number
  fn: () => void
  intervalMs: number | null
}

class VirtualClock {
  private current = 0
  private nextId = 1
  private tasks: ScheduledTask[] = []

  now(): number {
    return this.current
  }

  setTimeout = (fn: () => void, ms = 0): number => {
    const id = this.nextId++
    this.tasks.push({ id, dueAt: this.current + ms, fn, intervalMs: null })
    return id
  }

  setInterval = (fn: () => void, ms: number): number => {
    const id = this.nextId++
    this.tasks.push({ id, dueAt: this.current + ms, fn, intervalMs: ms })
    return id
  }

  clearTimeout = (id: number): void => {
    this.tasks = this.tasks.filter((t) => t.id !== id)
  }

  clearInterval = this.clearTimeout

  /**
   * Advance virtual time, running due tasks in order.
   *
   * Pending promise callbacks are flushed before each scan, because awaiting
   * code often registers its next timer only once an earlier step resolves.
   */
  async advance(ms: number): Promise<void> {
    const target = this.current + ms
    for (;;) {
      await flush()
      const due = this.tasks
        .filter((t) => t.dueAt <= target)
        .sort((a, b) => a.dueAt - b.dueAt)[0]
      if (!due) break

      this.current = Math.max(this.current, due.dueAt)
      if (due.intervalMs === null) this.tasks = this.tasks.filter((t) => t.id !== due.id)
      else due.dueAt = this.current + due.intervalMs

      due.fn()
    }
    this.current = target
    await flush()
  }
}

/** Let every pending promise callback run before virtual time moves again. */
export function flush(): Promise<void> {
  return new Promise((resolve) =>
    setImmediate(() => setImmediate(() => setImmediate(resolve))),
  )
}

export const clock = new VirtualClock()

class MemoryStorage {
  private map = new Map<string, string>()
  getItem(key: string): string | null {
    return this.map.has(key) ? (this.map.get(key) as string) : null
  }
  setItem(key: string, value: string): void {
    this.map.set(key, value)
  }
  removeItem(key: string): void {
    this.map.delete(key)
  }
  clear(): void {
    this.map.clear()
  }
}

export const storage = new MemoryStorage()

// A distinct object rather than globalThis, so Node's own timers stay intact
// for microtask flushing.
const fakeWindow: Record<string, unknown> = {
  localStorage: storage,
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => true,
}

const globals = globalThis as unknown as Record<string, unknown>
globals.window = fakeWindow
globals.document = {
  readyState: 'complete',
  addEventListener: () => {},
  removeEventListener: () => {},
}
globals.performance = { now: () => clock.now() }

/**
 * Point every timer at virtual time.
 *
 * The SDK installs its own shadow timers on `window` when it loads, so this has
 * to be called again after the app modules are imported.
 */
export function installTimers(): void {
  fakeWindow.setTimeout = clock.setTimeout
  fakeWindow.clearTimeout = clock.clearTimeout
  fakeWindow.setInterval = clock.setInterval
  fakeWindow.clearInterval = clock.clearInterval

  // Some call sites use bare `setTimeout`; route those through virtual time too.
  // `setImmediate` stays real, which is what microtask flushing relies on.
  globals.setTimeout = clock.setTimeout
  globals.clearTimeout = clock.clearTimeout
  globals.setInterval = clock.setInterval
  globals.clearInterval = clock.clearInterval
}

installTimers()
