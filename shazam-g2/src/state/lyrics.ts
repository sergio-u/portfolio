import { parseLrc } from './lrc'
import type { PlainLyrics, SyncedLyrics, Track } from '../glass/shared'

interface LrclibHit {
  plainLyrics?: string | null
  syncedLyrics?: string | null
}

export async function fetchSyncedLyrics(track: Track): Promise<SyncedLyrics | null> {
  const params = new URLSearchParams({
    artist_name: track.artist,
    track_name: track.title,
  })
  if (track.album) params.set('album_name', track.album)
  if (track.durationMs) params.set('duration', String(Math.round(track.durationMs / 1000)))

  const res = await fetch(`https://lrclib.net/api/get?${params.toString()}`)
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`LRCLIB HTTP ${res.status}`)

  const body = (await res.json()) as LrclibHit
  if (!body.syncedLyrics) return null

  const lines = parseLrc(body.syncedLyrics)
  if (lines.length === 0) return null

  return { kind: 'synced', lines, currentIndex: 0, scrollMode: 'auto' }
}

export async function fetchPlainLyrics(track: Track): Promise<PlainLyrics | null> {
  // Try LRCLIB plain first (same call, smaller response).
  const params = new URLSearchParams({
    artist_name: track.artist,
    track_name: track.title,
  })
  if (track.album) params.set('album_name', track.album)

  try {
    const res = await fetch(`https://lrclib.net/api/get?${params.toString()}`)
    if (res.ok) {
      const body = (await res.json()) as LrclibHit
      if (body.plainLyrics) return splitToLines(body.plainLyrics)
    }
  } catch {
    // fall through
  }

  // Fallback: lyrics.ovh (unofficial Genius scraper, best-effort).
  const url = `https://api.lyrics.ovh/v1/${encodeURIComponent(track.artist)}/${encodeURIComponent(track.title)}`
  const ovh = await fetch(url)
  if (!ovh.ok) return null
  const payload = (await ovh.json()) as { lyrics?: string }
  if (!payload.lyrics) return null
  return splitToLines(payload.lyrics)
}

function splitToLines(text: string): PlainLyrics {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)
  return { kind: 'plain', lines, currentIndex: 0 }
}

// TODO(future): Tidal lyrics via /tracks/{id}/lyrics (requires OAuth + registered app).
