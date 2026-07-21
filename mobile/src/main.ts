import { createApp } from 'vue';
import { createPinia } from 'pinia';
import { IonicVue, toastController } from '@ionic/vue';
import { App as CapacitorApp } from '@capacitor/app';
import { Network } from '@capacitor/network';

import '@ionic/vue/css/core.css';
import '@ionic/vue/css/normalize.css';
import '@ionic/vue/css/structure.css';
import '@ionic/vue/css/typography.css';
import '@ionic/vue/css/padding.css';
import './theme/variables.css';

import App from './App.vue';
import router from './router';
import { useAuthStore } from './stores/auth';
import { useMessagesStore } from './stores/messages';
import { useSocketStore } from './stores/socket';
import { i18n, translate } from './i18n';

const pinia = createPinia();
const app = createApp(App).use(pinia).use(i18n).use(IonicVue).use(router);

useAuthStore(pinia).listenForTokenRefresh();

function resumeDelivery() {
  const auth = useAuthStore(pinia);
  if (!auth.isAuthenticated) return;
  void useSocketStore(pinia).connect();
  void useMessagesStore(pinia).flushOutbox();
}

void Network.addListener('networkStatusChange', (status) => {
  if (status.connected) resumeDelivery();
});
void CapacitorApp.addListener('resume', resumeDelivery);
window.addEventListener('online', resumeDelivery);

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
      message: translate('app.pressAgainToExit'),
      duration: 1500,
      position: 'bottom'
    });
    await toast.present();
    return;
  }
  if (canGoBack) router.back();
});
