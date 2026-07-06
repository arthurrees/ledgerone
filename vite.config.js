import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Add your ngrok tunnel host here if exposing the dev server for Plaid OAuth institutions.
    // allowedHosts: ['your-tunnel.ngrok-free.dev'],
    proxy: {
      '/api': 'http://localhost:8787',
      '/health': 'http://localhost:8787',
    },
  },
})
