import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:3000',
      '/chat': { target: 'http://localhost:3000', changeOrigin: true },
      '/save': 'http://localhost:3000',
      '/context': 'http://localhost:3000',
    },
  },
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
})
