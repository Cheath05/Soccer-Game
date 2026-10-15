/**
 * European competitions have fixed colours, matching the League page's
 * European places, so a Champions League fixture is blue everywhere.
 */
export const EUROPE_COLOR: Record<string, string> = { UCL: 'blue', UEL: 'orange', UECL: 'green' }

/**
 * Every other competition hashes into this palette, which leaves out blue, orange, green and
 * yellow (the transfer-window line). The order keeps the English league and cups apart.
 */
const DOMESTIC_PALETTE = ['pink', 'cyan', 'indigo', 'gray', 'violet', 'red', 'grape']

function hash(text: string): number {
  let h = 0
  for (const ch of text) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return h
}

/** A competition keeps one colour wherever it shows. */
export function competitionColor(key: string): string {
  return EUROPE_COLOR[key] ?? DOMESTIC_PALETTE[hash(key) % DOMESTIC_PALETTE.length]
}
