<template>
  <ion-item button detail @click="$emit('open', conversation.id)">
    <Avatar slot="start" :name="peer?.display_name || t('common.user')" :url="peer?.avatar_url" />
    <ion-label>
      <h2>{{ peer?.display_name || t('common.unknownUser') }}</h2>
      <p>{{ preview }}</p>
    </ion-label>
    <div class="meta" slot="end">
      <span>{{ time }}</span>
      <ion-badge v-if="conversation.unread_count">{{ conversation.unread_count }}</ion-badge>
    </div>
  </ion-item>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { IonBadge, IonItem, IonLabel } from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import type { Conversation, Message } from '@/api/types';
import Avatar from '@/components/users/Avatar.vue';
import { useAuthStore } from '@/stores/auth';

const props = defineProps<{ conversation: Conversation }>();
defineEmits<{ open: [id: string] }>();
const auth = useAuthStore();
const { d, t } = useI18n();
const peer = computed(() => props.conversation.participants.find((user) => user.id !== auth.user?.id));

function messagePreview(message: Message): string {
  if (message.deleted_at) return t('message.deleted');
  if (message.text?.trim()) return message.text.trim();
  const attachment = message.attachments?.[0];
  if (attachment?.mime_type.startsWith('image/')) return t('message.image');
  if (attachment) return t('message.attachment');
  return t('message.generic');
}

const preview = computed(() => {
  const message = props.conversation.latest_message;
  if (!message) return t('conversations.noMessages');
  const value = messagePreview(message);
  return message.sender_id === auth.user?.id ? t('conversations.ownPreview', { message: value }) : value;
});
const time = computed(() => {
  const value = props.conversation.latest_message?.created_at || props.conversation.updated_at;
  return d(new Date(value), 'time');
});
</script>

<style scoped>
.meta {
  display: grid;
  gap: 6px;
  justify-items: end;
  font-size: 12px;
  color: var(--relay-muted);
}
</style>
