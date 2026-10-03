import react from '@vitejs/plugin-react'
import { configDefaults, defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
  test: {
    environment: 'jsdom',
    globals: true,
    pool: 'threads',
    maxWorkers: 1,
    fileParallelism: false,
    isolate: false,
    exclude: [...configDefaults.exclude, 'e2e/**'],
    setupFiles: ['./src/test/setup.ts'],
  },
})
