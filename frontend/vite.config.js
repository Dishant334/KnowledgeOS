import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Pinned to 5173: that is the address the backend allows by default (CORS_ORIGINS in backend/.env.example).
  server: { port: 5173, strictPort: true },
  // Vitest (npm test): runs every src/**/*.test.js(x) file in jsdom, a browser simulated in Node.
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    css: false, // styles are not needed to test behaviour
    restoreMocks: true, // every vi.spyOn is undone after each test
  },
})
