// The server an e2e script drives: its first argument, or the throwaway test server on :8765.
//
// Every script starts a new career, which overwrites save slot 1. So before any browser starts,
// the server must confirm (GET /api/health) that it doesn't keep its saves in the default
// folder, where the user's own careers live. A server that can't say, such as an older build,
// is refused too, and so is port 8000 (the user's game) without even asking. That also covers
// the Vite dev and preview servers, which pass /api through to :8000.
// FOOTSIM_E2E_ALLOW_REAL_SAVES=1 overrides all of it: never set it for the user's game.
export async function target(arg) {
  const base = arg || 'http://127.0.0.1:8765' // an empty argument counts as none
  if (process.env.FOOTSIM_E2E_ALLOW_REAL_SAVES === '1') return base
  if (new URL(base).port === '8000') refuse(base, "port 8000 is the user's game")
  let health = null
  try {
    const response = await fetch(new URL('/api/health', base))
    health = response.ok ? await response.json() : null
  } catch {
    health = null
  }
  if (health?.default_saves !== false) {
    refuse(base, health?.default_saves === true
      ? `it keeps its saves in the default folder, ${health.saves_dir}`
      : "it can't say where it keeps its saves (is it running, and up to date?)")
  }
  return base
}

function refuse(base, why) {
  console.error(
    `Refusing to run against ${base}: ${why}. Starting a career there would overwrite save ` +
      'slot 1. Use a throwaway server on :8765 with a temporary FOOTSIM_SAVES_DIR (see the ' +
      'run-footsim skill).',
  )
  process.exit(2)
}
