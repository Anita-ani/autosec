import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/auth':     'http://localhost:8000',
      '/alerts':   'http://localhost:8000',
      '/events':   'http://localhost:8000',
      '/stats':    'http://localhost:8000',
      '/block-ip': 'http://localhost:8000',
      '/webhooks': 'http://localhost:8000',
      '/replay':   'http://localhost:8000',
      '/health':   'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
