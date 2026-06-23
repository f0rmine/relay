import { Capacitor } from '@capacitor/core';
import { LocalNotifications } from '@capacitor/local-notifications';
import type { Message } from '@/api/types';
import { openConversation } from '@/services/navigation';
import { translate } from '@/i18n';

const MESSAGE_CHANNEL_ID = 'messages';

let initialized = false;
let permissionGranted = false;

async function createMessageChannel(): Promise<void> {
  await LocalNotifications.createChannel({
    id: MESSAGE_CHANNEL_ID,
    name: translate('notifications.channelName'),
    description: translate('notifications.channelDescription'),
    importance: 4,
    visibility: 1,
    vibration: true
  }).catch(() => undefined);
}

window.addEventListener('relay:locale-changed', () => {
  if (initialized && Capacitor.isNativePlatform()) void createMessageChannel();
});

async function ensurePermission(): Promise<boolean> {
  if (permissionGranted) return true;
  if (!Capacitor.isNativePlatform()) return false;

  let status = await LocalNotifications.checkPermissions();
  if (status.display !== 'granted') {
    status = await LocalNotifications.requestPermissions();
  }
  permissionGranted = status.display === 'granted';
  return permissionGranted;
}

export async function initNotifications(): Promise<void> {
  if (initialized || !Capacitor.isNativePlatform()) return;
  initialized = true;

  await ensurePermission();
  await createMessageChannel();

  await LocalNotifications.addListener('localNotificationActionPerformed', (event) => {
    const conversationId = event.notification.extra?.conversationId;
    if (conversationId) openConversation(conversationId);
  });
}

function notificationId(messageId: string): number {
  let hash = 0;
  for (let index = 0; index < messageId.length; index += 1) {
    hash = (hash * 31 + messageId.charCodeAt(index)) | 0;
  }
  return Math.abs(hash) || Date.now() % 2147483647;
}

function messagePreview(message: Message): string {
  if (message.deleted_at) return translate('message.deleted');
  if (message.text?.trim()) return message.text.trim();
  const attachment = message.attachments?.[0];
  if (attachment?.mime_type.startsWith('image/')) return translate('message.image');
  return attachment ? translate('message.attachment') : translate('message.generic');
}

export async function notifyNewMessage(message: Message, senderName: string): Promise<void> {
  if (!(await ensurePermission())) return;

  await LocalNotifications.schedule({
    notifications: [
      {
        id: notificationId(message.id),
        title: senderName,
        body: messagePreview(message),
        channelId: MESSAGE_CHANNEL_ID,
        group: `conversation:${message.conversation_id}`,
        extra: {
          conversationId: message.conversation_id,
          messageId: message.id
        }
      }
    ]
  });
}

export async function clearLocalConversationNotifications(conversationId: string): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;

  const delivered = await LocalNotifications.getDeliveredNotifications().catch(() => ({ notifications: [] }));
  const notifications = delivered.notifications.filter((notification) => {
    const dataConversationId = notification.data?.conversationId || notification.extra?.conversationId;
    return notification.group === `conversation:${conversationId}` || dataConversationId === conversationId;
  });
  if (notifications.length) {
    await LocalNotifications.removeDeliveredNotifications({ notifications }).catch(() => undefined);
  }
}
