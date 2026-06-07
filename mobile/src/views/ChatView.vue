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
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { IonContent, IonHeader, IonPage } from '@ionic/vue';
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
const conversationId = route.params.id as string;
const auth = useAuthStore();
const conversations = useConversationsStore();
const messages = useMessagesStore();
const socket = useSocketStore();
const sending = ref(false);
const error = ref('');

const conversation = computed(() => conversations.items.find((item) => item.id === conversationId));
const peer = computed(() => conversation.value?.participants.find((user) => user.id !== auth.user?.id));
const isPeerTyping = computed(() => Boolean(peer.value && messages.typing[conversationId]?.[peer.value.id]));

onMounted(async () => {
  try {
    if (!conversation.value) await conversations.fetchAll();
    socket.join(conversationId);
    await messages.fetch(conversationId);
    messages.read(conversationId);
    conversations.markRead(conversationId);
    void clearLocalConversationNotifications(conversationId);
    void clearPushConversationNotifications(conversationId);
  } catch (err: unknown) {
    error.value = displayError(err, 'Chat loading failed');
  }
});

onUnmounted(() => socket.leave(conversationId));

async function send(text: string, file: File | null) {
  sending.value = true;
  error.value = '';
  try {
    if (!socket.canSendRealtime()) {
      socket.connect();
      throw new Error('Realtime connection is not ready. Wait a moment and try again.');
    }
    const attachments = file ? [await messages.upload(file, conversationId)] : [];
    messages.send(conversationId, text, attachments);
  } catch (err: unknown) {
    error.value = displayError(err, 'Message send failed');
  } finally {
    sending.value = false;
  }
}

function typing(active: boolean) {
  socket.send(active ? 'typing:start' : 'typing:stop', { conversation_id: conversationId });
}

async function deleteMessage(messageId: string) {
  error.value = '';
  try {
    await messages.delete(messageId);
  } catch (err: unknown) {
    error.value = displayError(err, 'Message delete failed');
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
