import { execFileSync } from 'node:child_process'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// What a git command prints, or null if git is missing or it fails.
function git(...args: string[]): string | null {
  try {
    return execFileSync('git', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim() || null
  } catch {
    return null
  }
}

// The commit this build was made from. The version tag in the game shows it beside the server's
// own commit, so a page that wasn't rebuilt after an update shows up.
function buildCommit(): string {
  return git('rev-parse', '--short', 'HEAD') ?? 'unknown'
}

// The version number this build was made at, worked out as backend/src/footsim/core/build_info.py
// does: MAJOR from the latest git tag named like v1.0, MINOR the commits since it ("1.12"; "1.0"
// on the tag itself); with no tag "0." and the commit count; without git, FOOTSIM_VERSION.
function buildVersion(): string {
  const match = git('describe', '--tags', '--match', 'v[0-9]*', '--long')?.match(/^v(\d+)(?:\.\d+)*-(\d+)-g[0-9a-f]+$/)
  if (match) return `${match[1]}.${match[2]}`
  const commits = git('rev-list', '--count', 'HEAD')
  if (commits && /^\d+$/.test(commits)) return `0.${commits}`
  return process.env.FOOTSIM_VERSION || 'unknown'
}

// The backend binds to 127.0.0.1 only; the dev server proxies API and WebSocket traffic to it.
export default defineConfig({
  plugins: [react()],
  define: {
    __BUILD_VERSION__: JSON.stringify(buildVersion()),
    __BUILD_COMMIT__: JSON.stringify(buildCommit()),
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        ws: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
