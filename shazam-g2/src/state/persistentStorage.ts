// Bridge-aware persistent KV.
//
// `window.localStorage` is the source of truth *within a session* (sync read,
// fast). `bridge.setLocalStorage` / `bridge.getLocalStorage` is the host-side
// store that survives a packaged-.ehpk restart that clears the WebView's
// localStorage. Every set writes to both; on app boot, `hydrateFromBridge`
// pulls anything the host has that local doesn't.
//
// In browser dev (no bridge) the bridge calls silently no-op — localStorage
// alone behaves exactly as before.

import { waitForEvenAppBridge, type EvenAppBridge } from '@evenrealities/even_hub_sdk'

let bridgePromise: Promise<EvenAppBridge | null> | null = null

function getBridge(): Promise<EvenAppBridge | null> {
  if (!bridgePromise) {
    bridgePromise = Promise.race([
      waitForEvenAppBridge().catch(() => null),
      new Promise<null>((resolve) => setTimeout(() => resolve(null), 3000)),
    ])
  }
  return bridgePromise
}

export function persistentGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

export function persistentSet(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // ignore — non-fatal, runtime preference still applies for this session
  }
  void writeToBridge(key, value)
}

export function persistentRemove(key: string): void {
  try {
    window.localStorage.removeItem(key)
  } catch {
    // ignore
  }
  // SDK has no removeLocalStorage; empty string is the "absent" sentinel and
  // hydrateFromBridge treats it accordingly.
  void writeToBridge(key, '')
}

async function writeToBridge(key: string, value: string): Promise<void> {
  try {
    const bridge = await getBridge()
    if (!bridge) return
    await bridge.setLocalStorage(key, value)
  } catch {
    // bridge unavailable (browser dev) — localStorage is the only store
  }
}

/**
 * After the bridge resolves, fill in any keys that the local cache is missing
 * with whatever the host has stored. Called once at app boot. Calls
 * `onApply(key, value)` for each key it actually restored so subscribers can
 * re-render. Keys already present locally are skipped (the live session wins
 * over a possibly-stale host copy).
 */
export async function hydrateFromBridge(
  keys: readonly string[],
  onApply: (key: string, value: string) => void,
): Promise<void> {
  const bridge = await getBridge()
  if (!bridge) return
  for (const key of keys) {
    if (persistentGet(key) !== null) continue
    try {
      const remote = await bridge.getLocalStorage(key)
      if (remote && remote !== '') {
        try {
          window.localStorage.setItem(key, remote)
        } catch {
          // ignore
        }
        onApply(key, remote)
      }
    } catch {
      // skip this key
    }
  }
}
