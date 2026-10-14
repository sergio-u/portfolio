#!/usr/bin/env node
// scripts/sidecar.mjs
//
// Captures the laptop's microphone via ffmpeg and broadcasts 16 kHz mono
// S16LE PCM frames to WebSocket clients. Used by subtitles-g2 when the user
// selects "Mic: Sidecar" — useful when the desktop mic is better than the
// G2 glasses mic for music recognition.
//
// Run alongside `npm run dev`:
//   npm run dev:sidecar
//
// Then add the printed URL to .env.local:
//   VITE_SIDECAR_URL=ws://<your-lan-ip>:5174
//
// Requires ffmpeg on PATH. macOS default uses avfoundation; override the
// platform/input via SIDECAR_FFMPEG_INPUT for Linux/Windows or to pick a
// non-default audio device.

import { spawn, spawnSync } from 'node:child_process'
import os from 'node:os'
import { WebSocketServer } from 'ws'

const PORT = Number(process.env.SIDECAR_PORT) || 5174
const SAMPLE_RATE = 16_000

const argv = process.argv.slice(2)
const listMode = argv.includes('--list') || argv.includes('-l')
const deviceFlagIdx = argv.indexOf('--device')
const cliDevice = deviceFlagIdx >= 0 ? argv[deviceFlagIdx + 1] : undefined
const deviceIndex = cliDevice ?? process.env.SIDECAR_DEVICE

if (listMode) {
  listAudioDevices()
  process.exit(0)
}

function listAudioDevices() {
  if (process.platform !== 'darwin') {
    console.error('[sidecar] --list is only implemented for macOS / avfoundation.')
    console.error('  Linux:   arecord -l   (or pactl list short sources)')
    console.error('  Windows: ffmpeg -f dshow -list_devices true -i dummy')
    console.error('  Then set SIDECAR_FFMPEG_INPUT to the matching ffmpeg flags.')
    process.exit(1)
  }
  const r = spawnSync('ffmpeg', ['-f', 'avfoundation', '-list_devices', 'true', '-i', ''])
  const out = (r.stderr ?? Buffer.alloc(0)).toString()
  const audioHeaderIdx = out.indexOf('AVFoundation audio devices')
  if (audioHeaderIdx < 0) {
    console.error('[sidecar] could not parse ffmpeg device list. Raw output:\n' + out)
    process.exit(1)
  }
  const audioBlock = out.slice(audioHeaderIdx)
  const matches = [...audioBlock.matchAll(/\[(\d+)\]\s+(.+?)$/gm)]
  console.log('Audio input devices:')
  for (const m of matches) console.log(`  [${m[1]}] ${m[2].trim()}`)
  console.log('\nUse:  npm run dev:sidecar -- --device <index>')
  console.log('Or:   SIDECAR_DEVICE=<index> npm run dev:sidecar')
}

function ffmpegArgs() {
  // Override fully wins (any platform / any flag combo).
  //   SIDECAR_FFMPEG_INPUT='-f alsa -i default'
  //   SIDECAR_FFMPEG_INPUT='-f dshow -i audio=Microphone'
  //   SIDECAR_FFMPEG_INPUT='-f avfoundation -i :3'
  const override = process.env.SIDECAR_FFMPEG_INPUT
  if (override) {
    return ['-loglevel', 'error', ...override.split(' ').filter(Boolean), '-ar', String(SAMPLE_RATE), '-ac', '1', '-f', 's16le', '-']
  }
  // On avfoundation, `-i :0` is the *first-enumerated* device (often a
  // phantom Continuity Camera or inactive Bluetooth source — silent), not
  // the system default. Use `:default` when no explicit device is given.
  // See ffmpeg-devices docs and huggingface/transformers#28154.
  const dev = deviceIndex ?? null
  const platformDefault = process.platform === 'darwin'
    ? `-f avfoundation -i :${dev ?? 'default'}`
    : process.platform === 'linux'
      ? `-f alsa -i ${dev === null ? 'default' : `hw:${dev}`}`
      : process.platform === 'win32'
        ? `-f dshow -i audio=${dev === null ? 'default' : dev}`
        : null
  if (!platformDefault) {
    console.error(`[sidecar] unsupported platform ${process.platform}; set SIDECAR_FFMPEG_INPUT manually`)
    process.exit(1)
  }
  return ['-loglevel', 'error', ...platformDefault.split(' ').filter(Boolean), '-ar', String(SAMPLE_RATE), '-ac', '1', '-f', 's16le', '-']
}

function lanIPs() {
  const out = []
  for (const list of Object.values(os.networkInterfaces())) {
    for (const iface of list ?? []) {
      if (iface.family === 'IPv4' && !iface.internal) out.push(iface.address)
    }
  }
  return out
}

let ffmpeg = null
let bytesThisInterval = 0
let peakAmplitudeThisInterval = 0
let statsTimer = null

function startCapture(broadcast) {
  if (ffmpeg && ffmpeg.exitCode === null) return
  console.log('[sidecar] starting ffmpeg capture')
  ffmpeg = spawn('ffmpeg', ffmpegArgs())
  ffmpeg.on('error', (err) => {
    if (err.code === 'ENOENT') {
      console.error('[sidecar] ffmpeg not found on PATH. brew install ffmpeg')
      process.exit(1)
    }
    console.error('[sidecar] ffmpeg error:', err)
  })
  ffmpeg.stderr.on('data', (chunk) => process.stderr.write(`[ffmpeg] ${chunk}`))
  ffmpeg.stdout.on('data', (chunk) => {
    bytesThisInterval += chunk.length
    // Track signal level so we can distinguish "capturing silence" from
    // "capturing nothing." Each sample is 16-bit signed little-endian.
    for (let i = 0; i < chunk.length - 1; i += 2) {
      const sample = chunk.readInt16LE(i) / 32768
      const abs = sample < 0 ? -sample : sample
      if (abs > peakAmplitudeThisInterval) peakAmplitudeThisInterval = abs
    }
    broadcast(chunk)
  })
  ffmpeg.on('close', (code) => {
    console.log(`[sidecar] ffmpeg exited (${code})`)
    ffmpeg = null
  })
  if (!statsTimer) {
    statsTimer = setInterval(() => {
      if (bytesThisInterval === 0 && (!ffmpeg || ffmpeg.exitCode !== null)) return
      const expected = SAMPLE_RATE * 2 // 16-bit mono
      const ratio = (bytesThisInterval / expected).toFixed(2)
      const peakDb = peakAmplitudeThisInterval > 0 ? (20 * Math.log10(peakAmplitudeThisInterval)).toFixed(1) : '-inf'
      console.log(`[sidecar] capture: ${bytesThisInterval} B/s (${ratio}x expected) peak ${peakDb} dBFS`)
      bytesThisInterval = 0
      peakAmplitudeThisInterval = 0
    }, 1000)
  }
}

function stopCapture() {
  if (ffmpeg && ffmpeg.exitCode === null) {
    console.log('[sidecar] no clients; stopping ffmpeg')
    ffmpeg.kill('SIGTERM')
  }
  if (statsTimer) {
    clearInterval(statsTimer)
    statsTimer = null
  }
}

const wss = new WebSocketServer({ port: PORT, host: '0.0.0.0' })
const broadcast = (chunk) => {
  for (const client of wss.clients) {
    if (client.readyState === client.OPEN) client.send(chunk)
  }
}

wss.on('listening', () => {
  const deviceLabel = process.env.SIDECAR_FFMPEG_INPUT
    ? `override (${process.env.SIDECAR_FFMPEG_INPUT})`
    : deviceIndex !== undefined
      ? `device ${deviceIndex} on ${process.platform}`
      : `system default on ${process.platform}`
  console.log(`[sidecar] WebSocket listening on :${PORT}`)
  console.log(`[sidecar] mic: ${deviceLabel}`)
  console.log('[sidecar] reachable URLs:')
  for (const ip of lanIPs()) console.log(`  ws://${ip}:${PORT}`)
  console.log(`  ws://localhost:${PORT}`)
  console.log(`[sidecar] add to .env.local:  VITE_SIDECAR_URL=ws://<your-lan-ip>:${PORT}`)
  console.log('[sidecar] tip: list devices with  npm run dev:sidecar -- --list')
  console.log('[sidecar] capture starts on first client connect')
})

wss.on('connection', (ws, req) => {
  const peer = req.socket.remoteAddress
  console.log(`[sidecar] client connected from ${peer} (${wss.clients.size} total)`)
  startCapture(broadcast)
  ws.on('close', () => {
    console.log(`[sidecar] client ${peer} disconnected (${wss.clients.size} remaining)`)
    if (wss.clients.size === 0) stopCapture()
  })
  ws.on('error', (err) => console.warn(`[sidecar] ws error for ${peer}:`, err.message))
})

process.on('SIGINT', () => {
  console.log('\n[sidecar] shutting down')
  stopCapture()
  wss.close(() => process.exit(0))
})
