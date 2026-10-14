// Lightweight module for cross-module "is the glasses bridge ready to accept
// audio/imu control" signal. The raw SDK's EvenAppBridge doesn't expose a
// "page created" bit, so the controller publishes it here after
// createStartUpPageContainer succeeds. audio.ts reads it to decide between
// GlassBridgeSource (bridge PCM events) and MicrophoneSource (browser mic).

let ready = false
const listeners = new Set<(ready: boolean) => void>()

export function setGlassReady(next: boolean) {
  if (ready === next) return
  ready = next
  for (const l of listeners) l(next)
}

export function isGlassReady(): boolean {
  return ready
}

export function waitForGlassReady(timeoutMs: number): Promise<boolean> {
  if (ready) return Promise.resolve(true)
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      listeners.delete(l)
      resolve(false)
    }, timeoutMs)
    const l = (next: boolean) => {
      if (!next) return
      clearTimeout(timer)
      listeners.delete(l)
      resolve(true)
    }
    listeners.add(l)
  })
}
