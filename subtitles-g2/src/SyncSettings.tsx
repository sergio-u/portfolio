import { useEffect, useState } from 'react'
import type { AppSnapshot } from './glass/shared'
import { setAsrAccessToken, setAsrConsent, setAsrUrl, setSyncEngine } from './state/store'
import { HAS_BUNDLED_ASR_KEY } from './state/asr'

/** Show the active credential source and request session-only cloud-audio consent. */
export function SyncSettings({ snap }: { snap: AppSnapshot }) {
  const [url, setUrl] = useState(snap.asrUrl)
  useEffect(() => setUrl(snap.asrUrl), [snap.asrUrl])
  return (
    <div className="space-y-3 text-sm">
      <label className="flex items-center gap-2">
        Sync method
        <select value={snap.syncEngine} onChange={(event) => setSyncEngine(event.target.value === 'offline' ? 'offline' : 'asr')}
          className="bg-surface border border-border rounded px-2 py-1">
          <option value="asr">Soniox (cloud)</option>
          <option value="offline">Offline (experimental)</option>
        </select>
      </label>
      {snap.syncEngine === 'asr' ? (
        <>
          {HAS_BUNDLED_ASR_KEY ? (
            <p className="text-text-dim">Soniox credential included in this internal build. No token server required.</p>
          ) : (
            <>
              <label className="block space-y-1">
                <span>Token server URL</span>
                <input type="text" value={url} onChange={(event) => setUrl(event.target.value)}
                  onBlur={() => setAsrUrl(url.trim())} autoCapitalize="none" spellCheck={false}
                  placeholder="https://your-server/api/asr-token"
                  className="w-full bg-transparent border border-border rounded p-2" />
              </label>
              <label className="block space-y-1">
                <span>Server access token (not your Soniox API key)</span>
                <input type="password" value={snap.asrAccessToken} autoComplete="off"
                  onChange={(event) => setAsrAccessToken(event.target.value.trim())}
                  className="w-full bg-transparent border border-border rounded p-2" />
              </label>
            </>
          )}
          <label className="flex items-start gap-2">
            <input type="checkbox" checked={snap.asrConsent}
              onChange={(event) => setAsrConsent(event.target.checked)} />
            <span>Allow short microphone recordings to be sent to Soniox for synchronization this session.</span>
          </label>
          <p className="text-text-dim">Each check streams 20-25 seconds. Upload consent resets when the app reloads.
            {!HAS_BUNDLED_ASR_KEY && ' Server access tokens are also cleared.'}
            {' '}Network failures leave playback running. Only original subtitle text appears on the glasses.</p>
        </>
      ) : <p className="text-text-dim">Experimental loudness-pattern matching. No audio upload. Music and repeated rhythms can confuse it.</p>}
    </div>
  )
}
