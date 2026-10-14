import { useEffect, useRef } from 'react'
import type { EvenAppBridge } from '@evenrealities/even_hub_sdk'
import { GlassesController } from './controller'
import { nudgeOffset, stop } from '../state/player'
import { findMyPlace, stopAutoSync, syncNow } from '../state/autosync'
import { getAppSnapshot, subscribe } from '../state/store'

/** Sync correction applied per scroll gesture on the glasses. */
const NUDGE_STEP_MS = 500

export function AppGlasses() {
  const controllerRef = useRef<GlassesController | null>(null)

  useEffect(() => {
    const controller = new GlassesController({
      getSnapshot: getAppSnapshot,
      onIntent(intent) {
        const snap = getAppSnapshot()
        switch (intent.kind) {
          // Tap does whatever the current state needs: find the film, or
          // re-check alignment once it has been found.
          case 'select':
            if (!snap.film) break
            if (snap.mode === 'playing') void syncNow()
            else void findMyPlace()
            break
          // Subtitles ahead of the dialogue -> scroll up to push them later.
          case 'scroll-up':
            if (snap.film) nudgeOffset(NUDGE_STEP_MS)
            break
          case 'scroll-down':
            if (snap.film) nudgeOffset(-NUDGE_STEP_MS)
            break
          case 'back':
            if (!snap.film || snap.mode === 'ready') {
              // Root-page double-tap — host expects shutdown call (03-events.md:162).
              const bridge = (window as unknown as { __evenBridge?: EvenAppBridge | null }).__evenBridge
              bridge?.shutDownPageContainer(1).catch(() => { /* best-effort */ })
            } else {
              stop()
            }
            break
          case 'system-exit':
            stop()
            break
          default:
            break
        }
      },
    })
    controllerRef.current = controller
    void controller.init()

    const unsub = subscribe(() => controller.notify())
    const onPageHide = () => stopAutoSync()
    window.addEventListener('pagehide', onPageHide)

    return () => {
      stopAutoSync()
      window.removeEventListener('pagehide', onPageHide)
      unsub()
      void controller.dispose()
      controllerRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return null
}
