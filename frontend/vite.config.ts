import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The backend binds to 127.0.0.1 only; the dev server proxies API and WebSocket traffic to it.
export default defineConfig({
  plugins: [react()],
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
