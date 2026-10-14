import { useEffect, useRef } from 'react'
import type { EvenAppBridge } from '@evenrealities/even_hub_sdk'
import { GlassesController } from './controller'
import { createPipeline, getPipeline } from '../state/pipeline'
import { getAppSnapshot, moveLyricIndex, subscribe } from '../state/store'

export function AppGlasses() {
  const controllerRef = useRef<GlassesController | null>(null)

  useEffect(() => {
    // Pipeline doesn't need a router navigate in the raw-SDK design — the glass
    // layout is driven by snapshot.mode, not URL. Provide a no-op for pipeline's
    // navigate plumbing so nothing downstream crashes.
    const pipeline = createPipeline(() => { /* no url navigation */ })

    const controller = new GlassesController({
      getSnapshot: getAppSnapshot,
      onIntent(intent) {
        const p = getPipeline()
        if (!p) return
        const snap = getAppSnapshot()
        switch (intent.kind) {
          case 'select':
            if (snap.mode === 'idle' || snap.mode === 'no-match' || snap.mode === 'error') {
              p.runRecognition()
            } else if (snap.lyrics?.kind === 'synced' && snap.lyrics.scrollMode === 'manual') {
              p.resyncLyrics()
            } else if (snap.mode === 'playing-synced' || snap.mode === 'playing-plain' || snap.mode === 'metadata-only') {
              p.runRecognition()
            }
            break
          case 'scroll-up':
            if (snap.lyrics) moveLyricIndex(-1)
            break
          case 'scroll-down':
            if (snap.lyrics) moveLyricIndex(1)
            break
          case 'back':
            if (snap.mode === 'idle') {
              // Root-page double-tap — host expects shutdown call (03-events.md:162).
              const bridge = (window as unknown as { __evenBridge?: EvenAppBridge | null }).__evenBridge
              bridge?.shutDownPageContainer(1).catch(() => { /* best-effort */ })
            } else {
              p.reset()
            }
            break
          case 'system-exit':
            p.reset()
            break
          default:
            break
        }
      },
    })
    controllerRef.current = controller
    void controller.init()

    const unsub = subscribe(() => controller.notify())

    return () => {
      unsub()
      void controller.dispose()
      controllerRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return null
}
