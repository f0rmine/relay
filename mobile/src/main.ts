import { createApp } from 'vue';
import { createPinia } from 'pinia';
import { IonicVue, toastController } from '@ionic/vue';
import { App as CapacitorApp } from '@capacitor/app';

import '@ionic/vue/css/core.css';
import '@ionic/vue/css/normalize.css';
import '@ionic/vue/css/structure.css';
import '@ionic/vue/css/typography.css';
import '@ionic/vue/css/padding.css';
import './theme/variables.css';

import App from './App.vue';
import router from './router';
import { useAuthStore } from './stores/auth';

const pinia = createPinia();
const app = createApp(App).use(pinia).use(IonicVue).use(router);

useAuthStore(pinia).listenForTokenRefresh();

router.isReady().then(() => {
  app.mount('#app');
});

window.addEventListener('relay:open-conversation', (event) => {
  const conversationId = (event as CustomEvent<{ conversationId?: string }>).detail?.conversationId;
  if (conversationId) router.push(`/chat/${conversationId}`);
});

window.addEventListener('relay:auth-expired', () => {
  if (router.currentRoute.value.meta.auth) {
    router.replace('/login');
  }
});

let lastMainBackPressAt = 0;

CapacitorApp.addListener('backButton', async ({ canGoBack }) => {
  if (router.currentRoute.value.path === '/conversations') {
    const now = Date.now();
    if (now - lastMainBackPressAt < 1800) {
      await CapacitorApp.exitApp();
      return;
    }
    lastMainBackPressAt = now;
    const toast = await toastController.create({
      message: 'Press again to exit',
      duration: 1500,
      position: 'bottom'
    });
    await toast.present();
    return;
  }
  if (canGoBack) router.back();
});
