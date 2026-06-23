<template>
  <ion-page>
    <ion-header>
      <ChatHeader :peer="peer" />
    </ion-header>
    <ion-content class="chat-content" :scroll-y="false">
      <ErrorState v-if="error" :message="error" class="chat-error" />
      <ChatWindow
        :messages="messages.byConversation[conversationId] || []"
        :current-user-id="auth.user?.id"
        :participants="conversation?.participants || []"
        :typing="isPeerTyping"
        :has-more="messages.hasMore[conversationId]"
        @older="messages.fetch(conversationId, true)"
        @delete-message="deleteMessage"
      />
    </ion-content>
    <MessageInput :sending="sending" @send="send" @typing="typing" />
  </ion-page>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { IonContent, IonHeader, IonPage } from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import { displayError } from '@/api/client';
import ChatHeader from '@/components/chat/ChatHeader.vue';
import ChatWindow from '@/components/chat/ChatWindow.vue';
import MessageInput from '@/components/chat/MessageInput.vue';
import ErrorState from '@/components/ErrorState.vue';
import { useAuthStore } from '@/stores/auth';
import { useConversationsStore } from '@/stores/conversations';
import { useMessagesStore } from '@/stores/messages';
import { useSocketStore } from '@/stores/socket';
import { clearLocalConversationNotifications } from '@/services/notifications';
import { clearPushConversationNotifications } from '@/services/push';

const route = useRoute();
const conversationId = computed(() => String(route.params.id));
const auth = useAuthStore();
const conversations = useConversationsStore();
const messages = useMessagesStore();
const socket = useSocketStore();
const sending = ref(false);
const error = ref('');
const { t } = useI18n();

const conversation = computed(() => conversations.items.find((item) => item.id === conversationId.value));
const peer = computed(() => conversation.value?.participants.find((user) => user.id !== auth.user?.id));
const isPeerTyping = computed(() => Boolean(
  peer.value && messages.typing[conversationId.value]?.[peer.value.id]
));
let loadSequence = 0;

async function loadConversation(id: string, previousId?: string) {
  const sequence = ++loadSequence;
  if (previousId) socket.leave(previousId);
  error.value = '';
  try {
    if (!conversations.items.some((item) => item.id === id)) await conversations.fetchAll();
    if (sequence !== loadSequence) return;
    socket.join(id);
    await messages.fetch(id);
    if (sequence !== loadSequence) return;
    messages.read(id);
    conversations.markRead(id);
    void clearLocalConversationNotifications(id);
    void clearPushConversationNotifications(id);
  } catch (err: unknown) {
    if (sequence !== loadSequence) return;
    error.value = displayError(err, t('chat.loadFailed'));
  }
}

watch(conversationId, (id, previousId) => {
  void loadConversation(id, previousId);
}, { immediate: true });

function handleSocketError(event: Event) {
  const detail = (event as CustomEvent<{ conversationId?: string; message?: string }>).detail;
  if (detail?.conversationId === conversationId.value && detail.message) {
    error.value = detail.message;
  }
}

onMounted(() => window.addEventListener('relay:socket-error', handleSocketError));
onUnmounted(() => {
  loadSequence += 1;
  socket.leave(conversationId.value);
  window.removeEventListener('relay:socket-error', handleSocketError);
});

async function send(
  text: string,
  file: File | null,
  complete: (accepted: boolean) => void
) {
  sending.value = true;
  error.value = '';
  let accepted = false;
  try {
    if (!socket.canSendRealtime()) {
      socket.connect();
      throw new Error(t('chat.realtimeUnavailable'));
    }
    const attachments = file ? [await messages.upload(file, conversationId.value)] : [];
    messages.send(conversationId.value, text, attachments);
    accepted = true;
  } catch (err: unknown) {
    error.value = displayError(err, t('chat.sendFailed'));
  } finally {
    sending.value = false;
    complete(accepted);
  }
}

function typing(active: boolean) {
  socket.sendNow(active ? 'typing:start' : 'typing:stop', {
    conversation_id: conversationId.value
  });
}

async function deleteMessage(messageId: string) {
  error.value = '';
  try {
    await messages.delete(messageId);
  } catch (err: unknown) {
    error.value = displayError(err, t('chat.deleteFailed'));
  }
}
</script>

<style scoped>
.chat-content {
  --background: #0e1621;
}
.chat-error {
  position: absolute;
  inset-inline: 8px;
  top: 8px;
  z-index: 3;
}
</style>
