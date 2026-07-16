import { defineConfig } from 'vite'
export default defineConfig({
  server: {
    port: 5191,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
      },
    },
  },
})
