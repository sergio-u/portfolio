import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { '/api/asr-token': { target: 'http://127.0.0.1:5175', changeOrigin: true } },
  },
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
    dedupe: ['react', 'react-dom', 'react-router', '@evenrealities/even_hub_sdk', 'upng-js'],
  },
})
