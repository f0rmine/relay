import { Capacitor } from '@capacitor/core';
import { PushNotifications } from '@capacitor/push-notifications';
import { apiFetch } from '@/api/client';
import { openConversation } from '@/services/navigation';

let initialized = false;
let currentToken: string | null = null;
let registering = false;

async function registerDeviceToken(token: string): Promise<void> {
  await apiFetch<void>('/devices/push-token', {
    method: 'POST',
    body: JSON.stringify({
      token,
      platform: Capacitor.getPlatform()
    })
  }).catch(() => undefined);
}

export async function initPushNotifications(): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;

  if (!initialized) {
    initialized = true;

    await PushNotifications.createChannel({
      id: 'messages',
      name: 'Messages',
      description: 'New chat message notifications',
      importance: 4,
      visibility: 1,
      vibration: true
    }).catch(() => undefined);

    await PushNotifications.addListener('registration', async (token) => {
      currentToken = token.value;
      await registerDeviceToken(token.value);
    });

    await PushNotifications.addListener('pushNotificationActionPerformed', (event) => {
      const conversationId = event.notification.data?.conversation_id;
      if (conversationId) openConversation(conversationId);
    });
  }

  const permissions = await PushNotifications.requestPermissions();
  if (permissions.receive === 'granted') {
    if (currentToken) {
      await registerDeviceToken(currentToken);
    }
    if (!registering) {
      registering = true;
      await PushNotifications.register()
        .catch(() => undefined)
        .finally(() => {
          registering = false;
        });
    }
  }
}

export async function unregisterPushNotifications(): Promise<void> {
  if (!currentToken || !Capacitor.isNativePlatform()) return;
  await apiFetch<void>('/devices/push-token', {
    method: 'DELETE',
    body: JSON.stringify({ token: currentToken })
  }).catch(() => undefined);
  currentToken = null;
}

export async function clearPushConversationNotifications(conversationId: string): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;

  const delivered = await PushNotifications.getDeliveredNotifications().catch(() => ({ notifications: [] }));
  const notifications = delivered.notifications.filter(
    (notification) => notification.data?.conversation_id === conversationId
  );
  if (notifications.length) {
    await PushNotifications.removeDeliveredNotifications({ notifications }).catch(() => undefined);
  }
}
