import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [vue()],
  build: {
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          ionic: ['@ionic/vue', '@ionic/vue-router', 'ionicons/icons'],
          capacitor: [
            '@capacitor/app',
            '@capacitor/core',
            '@capacitor/local-notifications',
            '@capacitor/push-notifications'
          ],
          vendor: ['vue', 'vue-router', 'pinia']
        }
      }
    }
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    host: '0.0.0.0',
    port: 5173
  }
});
