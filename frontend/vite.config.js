import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:5000',
      '/chat': { target: 'http://localhost:5000', changeOrigin: true },
      '/save': 'http://localhost:5000',
      '/context': 'http://localhost:5000',
    },
  },
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
})
