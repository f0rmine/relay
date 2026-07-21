<template>
  <div ref="scroller" class="window" @scroll.passive="onScroll">
    <ion-button v-if="hasMore" class="older" fill="clear" size="small" @click="$emit('older')">{{ t('chat.loadOlder') }}</ion-button>
    <MessageBubble
      v-for="message in messages"
      :key="message.id"
      :message="message"
      :own="message.sender_id === currentUserId"
      :sender-name="senderName(message.sender_id)"
      @delete="$emit('delete-message', message.id)"
      @retry="$emit('retry-message', message.client_message_id || '')"
      @remove="$emit('remove-pending', message.client_message_id || '')"
    />
    <TypingIndicator :visible="typing" />
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue';
import { IonButton } from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import type { Message, User } from '@/api/types';
import MessageBubble from './MessageBubble.vue';
import TypingIndicator from './TypingIndicator.vue';

const props = defineProps<{
  messages: Message[];
  currentUserId?: string;
  participants?: User[];
  typing: boolean;
  hasMore?: boolean;
}>();
const emit = defineEmits<{
  older: [];
  'delete-message': [messageId: string];
  'retry-message': [clientMessageId: string];
  'remove-pending': [clientMessageId: string];
}>();
const scroller = ref<HTMLElement | null>(null);
const preservingOlderScroll = ref(false);
const { t } = useI18n();
let previousScrollHeight = 0;

function senderName(senderId: string) {
  if (senderId === props.currentUserId) return t('common.you');
  return props.participants?.find((user) => user.id === senderId)?.display_name || t('common.user');
}

function scrollBottom() {
  nextTick(() => {
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight;
  });
}

function onScroll() {
  if (!scroller.value || scroller.value.scrollTop >= 40 || !props.hasMore || preservingOlderScroll.value) {
    return;
  }
  preservingOlderScroll.value = true;
  previousScrollHeight = scroller.value.scrollHeight;
  emit('older');
  window.setTimeout(() => {
    preservingOlderScroll.value = false;
  }, 1500);
}

watch(
  () => props.messages.length,
  () => {
    if (preservingOlderScroll.value) {
      nextTick(() => {
        if (scroller.value) {
          scroller.value.scrollTop = scroller.value.scrollHeight - previousScrollHeight;
        }
        preservingOlderScroll.value = false;
      });
      return;
    }
    scrollBottom();
  }
);
onMounted(scrollBottom);
</script>

<style scoped>
.window {
  height: 100%;
  overflow-y: auto;
  padding: 10px 0 12px;
  background: #0e1621;
}
.older {
  display: block;
  margin: 0 auto 8px;
}
</style>
