// Last.fm desktop-auth + scrobbling client.
// Spec: https://www.last.fm/api/desktopauth and https://www.last.fm/api/scrobbling

import { md5 } from './md5'
import { persistentGet, persistentRemove, persistentSet } from './persistentStorage'

const API_URL = 'https://ws.audioscrobbler.com/2.0/'
const AUTH_URL = 'https://www.last.fm/api/auth/'

export const LASTFM_SESSION_STORAGE_KEY = 'shazam-g2:lastfm-session'
export const LASTFM_SESSION_CHANGED_EVENT = 'shazam-g2:lastfm-session-changed'

// Backwards-compat alias used inside this file.
const SESSION_STORAGE_KEY = LASTFM_SESSION_STORAGE_KEY

function emitSessionChanged(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(LASTFM_SESSION_CHANGED_EVENT))
  }
}

export interface LastfmConfig {
  apiKey: string
  sharedSecret: string
}

export interface LastfmSession {
  username: string
  sessionKey: string
}

export interface ScrobbleTrack {
  artist: string
  track: string
  album?: string
  albumArtist?: string
  durationSeconds?: number
  /** Unix timestamp (seconds) when the track started playing. */
  timestampSeconds: number
}

export interface ScrobbleResult {
  accepted: number
  ignored: number
}

export function loadLastfmConfig(): LastfmConfig | null {
  const apiKey = import.meta.env.VITE_LASTFM_API_KEY
  const sharedSecret = import.meta.env.VITE_LASTFM_SHARED_SECRET
  if (!apiKey || !sharedSecret) return null
  return { apiKey, sharedSecret }
}

export function loadSession(): LastfmSession | null {
  try {
    const raw = persistentGet(SESSION_STORAGE_KEY)
    return raw ? (JSON.parse(raw) as LastfmSession) : null
  } catch {
    return null
  }
}

export function saveSession(session: LastfmSession): void {
  persistentSet(SESSION_STORAGE_KEY, JSON.stringify(session))
  emitSessionChanged()
}

export function clearSession(): void {
  persistentRemove(SESSION_STORAGE_KEY)
  emitSessionChanged()
}

// --- Pending auth flow (sessionStorage) ---------------------------------
// Persists the in-flight auth token + URL so a tab reload mid-flow doesn't
// force the user to start over. Cleared on successful exchange or cancel.

const PENDING_STORAGE_KEY = 'shazam-g2:lastfm-pending-auth'

export interface PendingAuth {
  token: string
  authUrl: string
}

export function loadPendingAuth(): PendingAuth | null {
  try {
    const raw = sessionStorage.getItem(PENDING_STORAGE_KEY)
    return raw ? (JSON.parse(raw) as PendingAuth) : null
  } catch {
    return null
  }
}

export function savePendingAuth(pending: PendingAuth): void {
  try {
    sessionStorage.setItem(PENDING_STORAGE_KEY, JSON.stringify(pending))
  } catch {
    // ignore — non-fatal
  }
}

export function clearPendingAuth(): void {
  try {
    sessionStorage.removeItem(PENDING_STORAGE_KEY)
  } catch {
    // ignore
  }
}

// --- Desktop auth flow ---------------------------------------------------
// 1. getAuthToken(config)  → token
// 2. open buildAuthUrl(config, token) in a new tab; user clicks Allow on Last.fm
// 3. fetchSession(config, token)  → { username, sessionKey }; saveSession(...)

export async function getAuthToken(config: LastfmConfig): Promise<string> {
  const res = await call<{ token: string }>(config, 'auth.getToken', {}, 'GET')
  return res.token
}

export function buildAuthUrl(config: LastfmConfig, token: string): string {
  const params = new URLSearchParams({ api_key: config.apiKey, token })
  return `${AUTH_URL}?${params}`
}

export async function fetchSession(
  config: LastfmConfig,
  token: string,
): Promise<LastfmSession> {
  const res = await call<{ session: { name: string; key: string } }>(
    config,
    'auth.getSession',
    { token },
    'GET',
  )
  return { username: res.session.name, sessionKey: res.session.key }
}

// --- Scrobbling ----------------------------------------------------------

export async function scrobble(
  config: LastfmConfig,
  session: LastfmSession,
  t: ScrobbleTrack,
): Promise<ScrobbleResult> {
  const res = await call<{ scrobbles: { '@attr'?: { accepted: number; ignored: number } } }>(
    config,
    'track.scrobble',
    {
      ...trackParams(t),
      timestamp: String(t.timestampSeconds),
      sk: session.sessionKey,
    },
    'POST',
  )
  const attr = res.scrobbles['@attr']
  return { accepted: attr?.accepted ?? 0, ignored: attr?.ignored ?? 0 }
}

function trackParams(t: ScrobbleTrack): Record<string, string> {
  const p: Record<string, string> = { artist: t.artist, track: t.track }
  if (t.album) p.album = t.album
  if (t.albumArtist) p.albumArtist = t.albumArtist
  if (t.durationSeconds) p.duration = String(t.durationSeconds)
  return p
}

// --- Transport -----------------------------------------------------------

async function call<T>(
  config: LastfmConfig,
  method: string,
  params: Record<string, string>,
  httpMethod: 'GET' | 'POST',
): Promise<T> {
  const signed: Record<string, string> = { ...params, api_key: config.apiKey, method }
  signed.api_sig = sign(signed, config.sharedSecret)
  signed.format = 'json'

  const body = new URLSearchParams(signed)
  const res =
    httpMethod === 'GET'
      ? await fetch(`${API_URL}?${body}`)
      : await fetch(API_URL, { method: 'POST', body })

  const json = (await res.json().catch(() => ({}))) as {
    error?: number
    message?: string
  } & T
  if (!res.ok && !json.error) throw new Error(`Last.fm HTTP ${res.status}`)
  if (json.error) throw new Error(`Last.fm error ${json.error}: ${json.message ?? ''}`)
  return json
}

// Spec: sort params alphabetically by key, concatenate key+value pairs,
// append shared secret, MD5. format and callback are excluded.
function sign(params: Record<string, string>, secret: string): string {
  const keys = Object.keys(params)
    .filter((k) => k !== 'format' && k !== 'callback')
    .sort()
  const concat = keys.map((k) => k + params[k]).join('') + secret
  return md5(concat)
}
