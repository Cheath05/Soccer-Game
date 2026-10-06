import { execSync } from 'node:child_process'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The commit this build was made from. The version tag in the game shows it beside the server's
// own commit, so a page that wasn't rebuilt after an update shows up.
function buildCommit(): string {
  try {
    const out = execSync('git rev-parse --short HEAD', { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] })
    return out.trim() || 'unknown'
  } catch {
    return 'unknown'
  }
}

// The backend binds to 127.0.0.1 only; the dev server proxies API and WebSocket traffic to it.
export default defineConfig({
  plugins: [react()],
  define: {
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
