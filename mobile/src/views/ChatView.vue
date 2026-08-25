<template>
  <ion-page>
    <ion-header>
      <ChatHeader :peer="peer" :conversation="conversation" @open-info="openGroupInfo" />
    </ion-header>
    <ion-content class="chat-content" :scroll-y="false">
      <ErrorState v-if="error" :message="error" class="chat-error" />
      <ChatWindow
        :messages="messages.byConversation[conversationId] || []"
        :conversation="conversation"
        :current-user-id="auth.user?.id"
        :participants="conversation?.participants || []"
        :typing="isPeerTyping"
        :peer-name="peerName"
        :has-more="messages.hasMore[conversationId]"
        :highlight-message-id="highlightMessageId"
        @older="messages.fetch(conversationId, true)"
        @delete-message="deleteMessage"
        @retry-message="messages.retry"
        @remove-pending="messages.removePending"
        @edit-message="startEdit"
        @reply-message="startReply"
        @react-message="reactMessage"
        @copy-message="copyMessage"
        @forward-message="startForward"
        @pin-message="pinMessage"
        @unpin-message="unpinMessage"
        @highlight-done="clearHighlight"
      />
    </ion-content>
    <MessageInput
      :key="conversationId + (editingMessage?.id || '')"
      :sending="sending"
      :editing-message="editingMessage"
      :reply-message="replyMessage"
      :initial-value="draft"
      @send="send"
      @typing="typing"
      @edit="submitEdit"
      @cancel-edit="cancelEdit"
      @reply-cancel="cancelReply"
      @draft="(value: string) => saveDraft(conversationId, value)"
    />
    <ion-action-sheet
      :is-open="forwardOpen"
      header="Forward to"
      :buttons="forwardButtons"
      css-class="relay-message-actions"
      @didDismiss="forwardOpen = false"
    />
  </ion-page>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { IonActionSheet, IonContent, IonHeader, IonPage } from '@ionic/vue';
import { useI18n } from 'vue-i18n';
import { Capacitor } from '@capacitor/core';
import { displayError } from '@/api/client';
import ChatHeader from '@/components/chat/ChatHeader.vue';
import ChatWindow from '@/components/chat/ChatWindow.vue';
import MessageInput from '@/components/chat/MessageInput.vue';
import type { EditingMessage } from '@/components/chat/MessageInput.vue';
import ErrorState from '@/components/ErrorState.vue';
import type { Conversation, Message } from '@/api/types';
import { apiBlob, apiFetch } from '@/api/client';
import { useAuthStore } from '@/stores/auth';
import { useConversationsStore } from '@/stores/conversations';
import { useMessagesStore } from '@/stores/messages';
import { useSocketStore } from '@/stores/socket';
import { clearLocalConversationNotifications } from '@/services/notifications';
import { clearPushConversationNotifications } from '@/services/push';
import { loadDraft, clearDraft, saveDraft } from '@/services/drafts';

const route = useRoute();
const conversationId = computed(() => String(route.params.id));
const auth = useAuthStore();
const conversations = useConversationsStore();
const messages = useMessagesStore();
const socket = useSocketStore();
const sending = ref(false);
const error = ref('');
const editingMessage = ref<EditingMessage | null>(null);
const replyMessage = ref<Message | null>(null);
const forwardOpen = ref(false);
let forwardingMessage: Message | null = null;
const highlightMessageId = ref<string | undefined>(
  typeof route.query.m === 'string' ? route.query.m : undefined
);
const draft = ref('');
const { t } = useI18n();

const conversation = computed(() => conversations.items.find((item) => item.id === conversationId.value));
const peer = computed(() => conversation.value?.participants.find((user) => user.id !== auth.user?.id));
const peerName = computed(() => {
  if (conversation.value?.kind === 'group') return conversation.value.title || '';
  return peer.value?.display_name || '';
});
const isPeerTyping = computed(() => Boolean(
  peer.value && messages.typing[conversationId.value]?.[peer.value.id]
));
let loadSequence = 0;

async function loadConversation(id: string, previousId?: string) {
  const sequence = ++loadSequence;
  if (previousId) {
    socket.leave(previousId);
    const previousDraft = messages.byConversation[previousId] ? undefined : undefined;
    void previousDraft;
  }
  error.value = '';
  editingMessage.value = null;
  replyMessage.value = null;
  draft.value = loadDraft(id);
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
    await messages.enqueue(conversationId.value, text, file, replyMessage.value?.id || null);
    accepted = true;
    if (!file) clearDraft(conversationId.value);
  } catch (err: unknown) {
    error.value = displayError(err, t('chat.sendFailed'));
  } finally {
    sending.value = false;
    replyMessage.value = null;
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

function startEdit(message: Message) {
  editingMessage.value = { id: message.id, text: message.text || '' };
}

function cancelEdit() {
  editingMessage.value = null;
}

async function submitEdit(text: string, complete: (accepted: boolean) => void) {
  if (!editingMessage.value) return;
  error.value = '';
  let accepted = false;
  try {
    await messages.edit(editingMessage.value.id, text);
    accepted = true;
    editingMessage.value = null;
  } catch (err: unknown) {
    error.value = displayError(err, t('chat.editFailed'));
  } finally {
    complete(accepted);
  }
}

function startReply(message: Message) {
  replyMessage.value = message;
}

function cancelReply() {
  replyMessage.value = null;
}

async function reactMessage(payload: { messageId: string; emoji: string }) {
  error.value = '';
  try {
    const updated = await apiFetch<Message>(`/messages/${payload.messageId}/react`, {
      method: 'PUT',
      body: JSON.stringify({ emoji: payload.emoji })
    });
    messages.upsert(updated);
  } catch (err: unknown) {
    error.value = displayError(err, t('chat.reactFailed'));
  }
}

async function copyMessage(message: Message) {
  if (!message.text) return;
  try {
    if (Capacitor.isNativePlatform()) {
      const { Clipboard } = await import('@capacitor/clipboard');
      await Clipboard.write({ string: message.text });
    } else {
      await navigator.clipboard.writeText(message.text);
    }
  } catch {
    // clipboard may be denied
  }
}

function startForward(message: Message) {
  forwardingMessage = message;
  forwardOpen.value = true;
}

const forwardButtons = computed(() => {
  const buttons: Array<{ text: string; role?: string; handler?: () => void }> = conversations.items
    .filter((item) => item.id !== conversationId.value)
    .map((item) => ({
      text:
        item.kind === 'group'
          ? item.title || t('conversations.groupChat')
          : item.participants.find((user) => user.id !== auth.user?.id)?.display_name ||
            t('common.user'),
      handler: () => void forwardTo(item)
    }));
  buttons.push({ text: t('common.cancel'), role: 'cancel' });
  return buttons;
});

async function forwardTo(target: Conversation) {
  const source = forwardingMessage;
  forwardingMessage = null;
  if (!source) return;
  try {
    if (source.undecryptable) return;
    const attachments = source.attachments || [];
    await messages.enqueue(
      target.id,
      attachments.length ? source.text || '' : source.text || '',
      null,
      null
    );
    for (const attachment of attachments) {
      if (attachment.mime_type.startsWith('image/') && attachment.public_url.startsWith('blob:') && attachment.id.startsWith('local-')) {
        continue;
      }
      try {
        const blob = await apiBlob(`/attachments/${attachment.id}/download`);
        const file = new File([blob], attachment.original_filename, { type: attachment.mime_type });
        await messages.enqueue(target.id, '', file, null);
      } catch {
        // skip attachments that fail to download
      }
    }
  } catch (err: unknown) {
    error.value = displayError(err, t('chat.sendFailed'));
  }
}

async function pinMessage(message: Message) {
  error.value = '';
  try {
    const updated = await apiFetch<Conversation>(`/conversations/${conversationId.value}/pin/${message.id}`, {
      method: 'PUT'
    });
    conversations.applyConversationInfo(updated);
  } catch (err: unknown) {
    error.value = displayError(err, t('chat.pinFailed'));
  }
}

async function unpinMessage(_message: Message) {
  error.value = '';
  try {
    const updated = await apiFetch<Conversation>(`/conversations/${conversationId.value}/pin`, {
      method: 'DELETE'
    });
    conversations.applyConversationInfo(updated);
  } catch (err: unknown) {
    error.value = displayError(err, t('chat.pinFailed'));
  }
}

function openGroupInfo() {
  if (conversation.value?.kind === 'group') {
    window.dispatchEvent(
      new CustomEvent('relay:navigate', { detail: `/chat/${conversationId.value}/info` })
    );
  }
}

function clearHighlight() {
  highlightMessageId.value = undefined;
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
