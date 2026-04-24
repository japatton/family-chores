/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Phase 3 placeholder. The Phase-2 refactor's only requirement is that
// this stage builds, the dev server boots, and the one vitest case
// passes — see DECISIONS §11 step 11.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    sourcemap: false,
    target: 'es2022',
  },
  test: {
    environment: 'happy-dom',
    globals: true,
    include: ['tests/**/*.test.{ts,tsx}'],
  },
})
