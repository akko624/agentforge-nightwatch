import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  root: fileURLToPath(new URL('./report-site', import.meta.url)),
  base: './',
  publicDir: false,
  plugins: [react()],
  build: { outDir: '../dist-report', emptyOutDir: true },
});
