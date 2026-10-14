#!/usr/bin/env node
// Authenticated token broker. Audio travels directly from the phone to Soniox.
import { createServer } from 'node:http'
import { createHash, timingSafeEqual } from 'node:crypto'

const apiKey = process.env.SONIOX_API_KEY
const accessToken = process.env.ASR_CLIENT_TOKEN
if (!apiKey || !accessToken || accessToken.length < 32) {
  throw new Error('Set SONIOX_API_KEY and ASR_CLIENT_TOKEN (at least 32 random characters) on the server')
}
const model = process.env.SONIOX_MODEL || 'stt-rt-v5'
const origins = new Set((process.env.ASR_ALLOWED_ORIGINS || '').split(',').map((s) => s.trim()).filter(Boolean))
const expected = createHash('sha256').update(`Bearer ${accessToken}`).digest()
let windowAt = 0
let requests = 0

const server = createServer(async (req, res) => {
  res.setHeader('Cache-Control', 'no-store')
  res.setHeader('X-Content-Type-Options', 'nosniff')
  const origin = req.headers.origin
  if (origin && origins.has(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin)
    res.setHeader('Vary', 'Origin')
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS')
    res.setHeader('Access-Control-Allow-Headers', 'Authorization')
  } else if (origin && origins.size) {
    res.writeHead(403).end()
    return
  }
  if (req.url !== '/api/asr-token') { res.writeHead(404).end(); return }
  if (req.method === 'OPTIONS') { res.writeHead(204).end(); return }
  if (req.method !== 'POST') { res.writeHead(405, { Allow: 'POST' }).end(); return }
  const supplied = createHash('sha256').update(req.headers.authorization || '').digest()
  if (!timingSafeEqual(supplied, expected)) { res.writeHead(401).end(); return }
  if (Date.now() - windowAt >= 60_000) { windowAt = Date.now(); requests = 0 }
  // Personal broker budget. Protect even an accidentally disclosed client token.
  if (++requests > 6) { res.writeHead(429, { 'Retry-After': '60' }).end(); return }
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 10_000)
  res.on('close', () => controller.abort())
  try {
    const response = await fetch('https://api.soniox.com/v1/auth/temporary-api-key', {
      method: 'POST',
      headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ usage_type: 'transcribe_websocket', expires_in_seconds: 60,
        single_use: true, max_session_duration_seconds: 90 }),
      signal: controller.signal,
      redirect: 'error',
    })
    if (!response.ok) { res.writeHead(502).end('Soniox authentication unavailable'); return }
    const key = await response.json()
    if (typeof key.api_key !== 'string' || !key.api_key) throw new Error('Invalid provider response')
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ api_key: key.api_key, model }))
  } catch {
    if (!res.destroyed) res.writeHead(502).end('Speech recognition service unavailable')
  } finally { clearTimeout(timeout) }
})
server.requestTimeout = 15_000
server.headersTimeout = 10_000
server.listen(Number(process.env.ASR_PORT || 5175), process.env.ASR_HOST || '127.0.0.1', () => {
  console.log('[asr] token broker ready; permanent credentials remain server-side')
})
