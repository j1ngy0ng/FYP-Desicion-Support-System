import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    resolve: { dedupe: ['react', 'react-dom'] },
    server: {
      fs: { allow: ['..'] },
      proxy: { '/api': env.VITE_API_TARGET || 'http://127.0.0.1:8000' },
    },
  }
})
