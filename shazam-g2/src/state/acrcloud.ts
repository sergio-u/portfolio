// ACRCloud Identification API client. Browser-direct; signs with HMAC-SHA1.
// Spec: https://docs.acrcloud.com/reference/identification-api/identification-api

import type { Track } from '../glass/shared'
import { hmacSha1Base64 } from './hmacSha1'

interface AcrCloudResponse {
  status: { code: number; msg?: string; version?: string }
  metadata?: {
    music?: AcrCloudMusic[]
  }
}

interface AcrCloudMusic {
  title: string
  artists?: { name: string }[]
  album?: { name?: string }
  duration_ms?: number
  /** Song position (ms) corresponding to where the match starts in the uploaded sample. */
  play_offset_ms?: number
  /** Offset (ms) within the uploaded sample at which the match starts. */
  sample_begin_time_offset_ms?: number
  external_metadata?: {
    isrc?: string
    spotify?: { id?: string; url?: string }
    apple_music?: { id?: string; url?: string }
    deezer?: { id?: string }
  }
}

const PATH = '/v1/identify'
const STATUS_NO_MATCH = 1001

export function isConfigured(): boolean {
  return Boolean(
    import.meta.env.VITE_ACRCLOUD_HOST &&
      import.meta.env.VITE_ACRCLOUD_ACCESS_KEY &&
      import.meta.env.VITE_ACRCLOUD_ACCESS_SECRET,
  )
}

export async function recognize(blob: Blob, clipStartedAt: number): Promise<Track | null> {
  const host = import.meta.env.VITE_ACRCLOUD_HOST as string | undefined
  const accessKey = import.meta.env.VITE_ACRCLOUD_ACCESS_KEY as string | undefined
  const accessSecret = import.meta.env.VITE_ACRCLOUD_ACCESS_SECRET as string | undefined
  if (!host || !accessKey || !accessSecret) {
    throw new Error('ACRCloud not configured — check .env.local')
  }

  const timestamp = Math.floor(Date.now() / 1000).toString()
  const stringToSign = ['POST', PATH, accessKey, 'audio', '1', timestamp].join('\n')
  const signature = hmacSha1Base64(accessSecret, stringToSign)
  const url = `https://${host}${PATH}`

  const form = new FormData()
  form.append('sample', blob, 'clip.wav')
  form.append('sample_bytes', String(blob.size))
  form.append('access_key', accessKey)
  form.append('data_type', 'audio')
  form.append('signature_version', '1')
  form.append('signature', signature)
  form.append('timestamp', timestamp)

  console.log('[acrcloud] POST', url, { sample_bytes: blob.size, timestamp })
  let res: Response
  try {
    res = await fetch(url, { method: 'POST', body: form })
  } catch (err) {
    console.warn('[acrcloud] fetch threw (CORS or network):', err)
    throw err
  }
  console.log('[acrcloud] http status', res.status)
  if (!res.ok) throw new Error(`ACRCloud HTTP ${res.status}`)
  const body = (await res.json()) as AcrCloudResponse
  console.log('[acrcloud] body', body)

  if (body.status.code === STATUS_NO_MATCH) return null
  if (body.status.code !== 0) throw new Error(body.status.msg ?? `ACRCloud error ${body.status.code}`)

  const music = body.metadata?.music?.[0]
  if (!music) return null
  if (!music.title || !music.artists?.[0]?.name) return null
  return flatten(music, clipStartedAt)
}

function flatten(m: AcrCloudMusic, clipStartedAt: number): Track {
  // ACRCloud's `play_offset_ms` is the song position at the *match start*,
  // which lives `sample_begin_time_offset_ms` into our uploaded clip — not
  // necessarily at offset 0. To anchor the clock at the clip's actual start
  // (which is what `recognizedAt` represents), back up by that offset.
  const playOffset = m.play_offset_ms ?? 0
  const sampleBegin = m.sample_begin_time_offset_ms ?? 0
  return {
    title: m.title,
    artist: m.artists?.[0]?.name ?? '',
    album: m.album?.name,
    durationMs: m.duration_ms,
    timecodeMs: Math.max(0, playOffset - sampleBegin),
    recognizedAt: clipStartedAt,
  }
}

