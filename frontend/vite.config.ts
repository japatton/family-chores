import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'

// The SPA is served under HA's Ingress at a variable base path (e.g.
// `/hassio/ingress/local_family_chores/`). We emit relative asset paths
// and let React Router's HashRouter handle in-app navigation — simpler
// than threading the Ingress path through BrowserRouter's basename.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: resolve(__dirname, '../backend/src/family_chores/static'),
    emptyOutDir: true,
    sourcemap: false,
    target: 'es2022',
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8099',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
