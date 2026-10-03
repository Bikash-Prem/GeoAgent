import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // Load keys from the repo-root .env (same file the backend uses).
  envDir: '..',
});
