/// <reference types="vitest" />
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  return {
    plugins: [react()],
    server: {
      host: '127.0.0.1',
      port: Number(env.VITE_PORT || 5173),
      strictPort: false, // if the port is taken, use the next free one instead of failing
    },
    preview: { host: '127.0.0.1', port: Number(env.VITE_PORT || 5173) + 100 },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      css: false,
    },
  };
});
