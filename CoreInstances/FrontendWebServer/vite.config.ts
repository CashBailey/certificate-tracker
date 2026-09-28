import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiBase = env.VITE_API_URL || '/api'
  const proxyTarget = env.VITE_API_PROXY_TARGET || 'http://api:8000'

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 3000,
      watch: {
        usePolling: true,
      },
      proxy: apiBase.startsWith('/')
        ? {
            [apiBase]: {
              target: proxyTarget,
              changeOrigin: true,
              rewrite: (path) => path.replace(new RegExp(`^${apiBase}`), ''),
            },
          }
        : undefined,
    },
  }
})
