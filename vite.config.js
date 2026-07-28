import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendUrl = env.LEDGERONE_BACKEND_URL || 'http://100.96.116.18:8787'

  return {
    plugins: [react()],
    server: {
      // Add your ngrok tunnel host here if exposing the dev server for Plaid OAuth institutions.
      // allowedHosts: ['your-tunnel.ngrok-free.dev'],
      proxy: {
        '/api': backendUrl,
        '/health': backendUrl,
      },
    },
  }
})
