import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Tailwind CSS v4 is compiled by PostCSS (see postcss.config.js), which behaves
// the same in dev and in production builds.
export default defineConfig({
  plugins: [react()],
})
