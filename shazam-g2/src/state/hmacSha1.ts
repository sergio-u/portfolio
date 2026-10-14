// Pure-JS HMAC-SHA1, base64 output.
// We can't use crypto.subtle because the Even App WebView loads our LAN dev
// URL over plain HTTP — that's not a "secure context", so Web Crypto is
// `undefined`. Same situation we already handled for MD5 in ./md5.ts.
// Reference: RFC 3174 (SHA-1), RFC 2104 (HMAC).

export function hmacSha1Base64(secret: string, message: string): string {
  const enc = new TextEncoder()
  return bytesToBase64(hmacSha1(enc.encode(secret), enc.encode(message)))
}

const BLOCK = 64

function hmacSha1(key: Uint8Array, message: Uint8Array): Uint8Array {
  let k = key.length > BLOCK ? sha1(key) : key
  if (k.length < BLOCK) {
    const padded = new Uint8Array(BLOCK)
    padded.set(k)
    k = padded
  }
  const ipad = new Uint8Array(BLOCK)
  const opad = new Uint8Array(BLOCK)
  for (let i = 0; i < BLOCK; i++) {
    ipad[i] = k[i] ^ 0x36
    opad[i] = k[i] ^ 0x5c
  }
  return sha1(concat(opad, sha1(concat(ipad, message))))
}

function sha1(bytes: Uint8Array): Uint8Array {
  const bitLen = bytes.length * 8
  const padLen = ((56 - ((bytes.length + 1) % 64)) + 64) % 64
  const padded = new Uint8Array(bytes.length + 1 + padLen + 8)
  padded.set(bytes)
  padded[bytes.length] = 0x80
  // 64-bit big-endian bit length. We only set the low 32 bits — high bits
  // remain zero, which is correct for any input under 512 MB.
  new DataView(padded.buffer).setUint32(padded.length - 4, bitLen >>> 0, false)

  let h0 = 0x67452301
  let h1 = 0xefcdab89
  let h2 = 0x98badcfe
  let h3 = 0x10325476
  let h4 = 0xc3d2e1f0

  const W = new Uint32Array(80)

  for (let chunk = 0; chunk < padded.length; chunk += BLOCK) {
    for (let i = 0; i < 16; i++) {
      const o = chunk + i * 4
      W[i] = ((padded[o] << 24) | (padded[o + 1] << 16) | (padded[o + 2] << 8) | padded[o + 3]) >>> 0
    }
    for (let i = 16; i < 80; i++) {
      W[i] = rotl32(W[i - 3] ^ W[i - 8] ^ W[i - 14] ^ W[i - 16], 1)
    }

    let a = h0
    let b = h1
    let c = h2
    let d = h3
    let e = h4
    for (let i = 0; i < 80; i++) {
      let f: number
      let k: number
      if (i < 20) {
        f = (b & c) | (~b & d)
        k = 0x5a827999
      } else if (i < 40) {
        f = b ^ c ^ d
        k = 0x6ed9eba1
      } else if (i < 60) {
        f = (b & c) | (b & d) | (c & d)
        k = 0x8f1bbcdc
      } else {
        f = b ^ c ^ d
        k = 0xca62c1d6
      }
      const temp = (rotl32(a, 5) + f + e + k + W[i]) >>> 0
      e = d
      d = c
      c = rotl32(b, 30)
      b = a
      a = temp
    }

    h0 = (h0 + a) >>> 0
    h1 = (h1 + b) >>> 0
    h2 = (h2 + c) >>> 0
    h3 = (h3 + d) >>> 0
    h4 = (h4 + e) >>> 0
  }

  const out = new Uint8Array(20)
  const view = new DataView(out.buffer)
  view.setUint32(0, h0, false)
  view.setUint32(4, h1, false)
  view.setUint32(8, h2, false)
  view.setUint32(12, h3, false)
  view.setUint32(16, h4, false)
  return out
}

function rotl32(x: number, n: number): number {
  return ((x << n) | (x >>> (32 - n))) >>> 0
}

function concat(a: Uint8Array, b: Uint8Array): Uint8Array {
  const out = new Uint8Array(a.length + b.length)
  out.set(a)
  out.set(b, a.length)
  return out
}

function bytesToBase64(bytes: Uint8Array): string {
  let s = ''
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i])
  return btoa(s)
}
