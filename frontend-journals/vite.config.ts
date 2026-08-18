import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
// Served by Flask's journals_bp at /journals (see src/blueprints/journals.py),
// so assets must resolve relative to that subpath, not the site root.
export default defineConfig({
  base: '/journals/',
  plugins: [react()],
  build: {
    outDir: 'dist',
  },
})
