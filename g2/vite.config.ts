import { defineConfig } from 'vite'

export default defineConfig({
  server: {
    host: true,
    hmr: {
      host: '10.183.86.110',
    },
  },
})
