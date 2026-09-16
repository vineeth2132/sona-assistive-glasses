import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  // Laptop-only overrides live in the git-ignored g2/.env.local:
  //   VITE_PI_WS=ws://localhost:8765/ws   (fake Pi, see dev/fake_pi.py)
  //   VITE_HMR_HOST=localhost
  const env = loadEnv(mode, process.cwd(), 'VITE_')

  return {
    server: {
      host: true,
      hmr: {
        host: env.VITE_HMR_HOST || '10.183.86.110',
      },
    },
  }
})
