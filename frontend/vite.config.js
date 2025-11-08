import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Use relative base so it works under GitHub Pages subpaths
export default defineConfig({
  plugins: [react()],
  base: './',
})
