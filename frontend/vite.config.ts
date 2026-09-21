import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The backend runs on 127.0.0.1:8000; /api is proxied so the UI works from one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': { target: process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
})
