import type { Track } from '../glass/shared'

interface AudDResponse {
  status: 'success' | 'error'
  result: AudDResult | null
  error?: { error_code: number; error_message: string }
}

interface AudDResult {
  artist: string
  title: string
  album?: string
  release_date?: string
  label?: string
  timecode?: string
  song_link?: string
  apple_music?: {
    url?: string
    durationInMillis?: number
    isrc?: string
  }
  spotify?: {
    duration_ms?: number
    external_ids?: { isrc?: string }
  }
  deezer?: {
    duration?: number
  }
}

export function isConfigured(): boolean {
  // AudD allows an empty token for ~300 anonymous trial requests, so the env
  // var being undefined is still a valid "configured" state.
  return import.meta.env.VITE_AUDD_TOKEN !== undefined
}

export async function recognize(blob: Blob, clipStartedAt: number): Promise<Track | null> {
  const form = new FormData()
  form.append('file', blob, 'clip.wav')
  form.append('api_token', import.meta.env.VITE_AUDD_TOKEN ?? '')
  form.append('return', 'apple_music,spotify,deezer')

  console.log('[audd] POST https://api.audd.io/', { sample_bytes: blob.size })
  const res = await fetch('https://api.audd.io/', { method: 'POST', body: form })
  console.log('[audd] http status', res.status)
  if (!res.ok) throw new Error(`AudD HTTP ${res.status}`)
  const body = (await res.json()) as AudDResponse
  console.log('[audd] body', body)
  if (body.status !== 'success') throw new Error(body.error?.error_message ?? 'AudD error')
  if (!body.result) return null
  if (!body.result.title || !body.result.artist) return null

  return flatten(body.result, clipStartedAt)
}

function flatten(r: AudDResult, clipStartedAt: number): Track {
  const timecodeMs = r.timecode ? parseTimecode(r.timecode) : 0
  const durationMs =
    r.apple_music?.durationInMillis ??
    r.spotify?.duration_ms ??
    (r.deezer?.duration ? r.deezer.duration * 1000 : undefined)

  return {
    title: r.title,
    artist: r.artist,
    album: r.album,
    durationMs,
    timecodeMs,
    // Anchor the lyric clock to when we started recording — AudD's timecode corresponds
    // to the track position at (approximately) the start of the uploaded clip.
    recognizedAt: clipStartedAt,
  }
}

function parseTimecode(tc: string): number {
  const parts = tc.split(':').map(Number)
  if (parts.some(Number.isNaN)) return 0
  let seconds = 0
  for (const p of parts) seconds = seconds * 60 + p
  return seconds * 1000
}
