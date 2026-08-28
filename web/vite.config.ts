import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // maplibre-gl crée un Web Worker interne via une URL relative à son propre
  // bundle ; le pré-bundling de Vite (optimizeDeps) casse cette résolution
  // (le worker échoue à charger silencieusement, et toute source GeoJSON
  // dépendant du worker ne rend jamais). On exclut donc le paquet.
  optimizeDeps: {
    exclude: ['maplibre-gl'],
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
