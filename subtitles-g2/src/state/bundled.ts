/**
 * Subtitles bundled into the build.
 *
 * Any `.srt` dropped into `bundled/` before a build is compiled into the app,
 * so a screening needs no import step and no file picker in a dark auditorium.
 * The files themselves are not committed.
 */

const files = import.meta.glob('/bundled/*.srt', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

export interface BundledSubtitles {
  /** File name without path or extension, used as the display title. */
  name: string
  text: string
}

export function listBundled(): BundledSubtitles[] {
  return Object.entries(files)
    .map(([path, text]) => ({
      name: (path.split('/').pop() ?? path).replace(/\.srt$/i, ''),
      text,
    }))
    .sort((a, b) => a.name.localeCompare(b.name))
}
