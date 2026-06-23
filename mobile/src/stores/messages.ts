import { defineStore } from 'pinia';
import { apiFetch } from '@/api/client';
import type { Attachment, Message } from '@/api/types';
import { useAuthStore } from '@/stores/auth';
import { useSocketStore } from '@/stores/socket';
import { translate } from '@/i18n';

interface MessagesState {
  byConversation: Record<string, Message[]>;
  cursors: Record<string, string | null>;
  hasMore: Record<string, boolean>;
  typing: Record<string, Record<string, boolean>>;
  loading: boolean;
}

const pendingTimers = new Map<string, ReturnType<typeof setTimeout>>();

function clearPendingTimer(requestId?: string) {
  if (!requestId) return;
  const timer = pendingTimers.get(requestId);
  if (timer) clearTimeout(timer);
  pendingTimers.delete(requestId);
}

function clearAllPendingTimers() {
  pendingTimers.forEach((timer) => clearTimeout(timer));
  pendingTimers.clear();
}

export const useMessagesStore = defineStore('messages', {
  state: (): MessagesState => ({
    byConversation: {},
    cursors: {},
    hasMore: {},
    typing: {},
    loading: false
  }),
  actions: {
    reset() {
      clearAllPendingTimers();
      this.byConversation = {};
      this.cursors = {};
      this.hasMore = {};
      this.typing = {};
      this.loading = false;
    },
    async fetch(conversationId: string, older = false) {
      this.loading = true;
      try {
        const cursor = older ? this.cursors[conversationId] : null;
        const params = cursor ? `?cursor=${encodeURIComponent(cursor)}` : '';
        const response = await apiFetch<{ items: Message[]; next_cursor: string | null; has_more: boolean }>(
          `/conversations/${conversationId}/messages${params}`
        );
        const ascending = response.items.reverse();
        this.byConversation[conversationId] = older
          ? [...ascending, ...(this.byConversation[conversationId] || [])]
          : ascending;
        this.cursors[conversationId] = response.next_cursor;
        this.hasMore[conversationId] = response.has_more;
      } finally {
        this.loading = false;
      }
    },
    async upload(file: File, conversationId?: string): Promise<Attachment> {
      const form = new FormData();
      form.append('file', file);
      if (conversationId) form.append('conversation_id', conversationId);
      return apiFetch<Attachment>('/attachments/upload', { method: 'POST', body: form });
    },
    send(conversationId: string, text: string, attachments: Attachment[] = []) {
      const auth = useAuthStore();
      const socket = useSocketStore();
      const cleanText = text.trim();
      const requestId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
      const sent = socket.sendNow('message:send', {
        conversation_id: conversationId,
        text: cleanText || null,
        attachment_ids: attachments.map((item) => item.id)
      }, requestId);
      if (!sent) {
        throw new Error(translate('chat.realtimeUnavailable'));
      }
      if (auth.user && (cleanText || attachments.length)) {
        this.addOptimistic(
          conversationId,
          auth.user.id,
          cleanText || null,
          attachments,
          requestId
        );
      }
      return requestId;
    },
    read(conversationId: string) {
      useSocketStore().send('message:read', { conversation_id: conversationId });
    },
    async delete(messageId: string) {
      const message = await apiFetch<Message>(`/messages/${messageId}`, { method: 'DELETE' });
      this.markDeleted(message);
    },
    upsert(message: Message) {
      clearPendingTimer(message.request_id);
      const list = this.byConversation[message.conversation_id] || [];
      const pendingIndex = message.request_id
        ? list.findIndex((item) => item.id === `pending-${message.request_id}`)
        : list.findIndex(
          (item) =>
            item.id.startsWith('pending-') &&
            item.sender_id === message.sender_id &&
            item.text === message.text
        );
      if (pendingIndex >= 0) list.splice(pendingIndex, 1);
      const index = list.findIndex((item) => item.id === message.id);
      if (index >= 0) list[index] = message;
      else list.push(message);
      list.sort((a, b) => {
        const timeDelta = +new Date(a.created_at) - +new Date(b.created_at);
        if (timeDelta !== 0) return timeDelta;
        if (a.id.startsWith('pending-') && !b.id.startsWith('pending-')) return 1;
        if (!a.id.startsWith('pending-') && b.id.startsWith('pending-')) return -1;
        return a.id.localeCompare(b.id);
      });
      this.byConversation[message.conversation_id] = list;
    },
    addOptimistic(
      conversationId: string,
      senderId: string,
      text: string | null,
      attachments: Attachment[] = [],
      requestId?: string
    ) {
      const now = new Date().toISOString();
      const tempId = requestId || globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
      this.upsert({
        id: `pending-${tempId}`,
        conversation_id: conversationId,
        sender_id: senderId,
        text,
        created_at: now,
        updated_at: now,
        edited_at: null,
        deleted_at: null,
        deleted_by_id: null,
        attachments,
        read_by: [],
        request_id: requestId
      });
      if (requestId) {
        clearPendingTimer(requestId);
        pendingTimers.set(requestId, setTimeout(() => {
          const conversation = this.failPending(requestId);
          if (conversation) {
            window.dispatchEvent(new CustomEvent('relay:socket-error', {
              detail: { conversationId: conversation, message: translate('chat.sendFailed') }
            }));
          }
        }, 15000));
      }
    },
    failPending(requestId: string): string | undefined {
      clearPendingTimer(requestId);
      for (const [conversationId, list] of Object.entries(this.byConversation)) {
        const index = list.findIndex((message) => message.id === `pending-${requestId}`);
        if (index >= 0) {
          list.splice(index, 1);
          return conversationId;
        }
      }
      return undefined;
    },
    markDeleted(message: Message) {
      this.upsert(message);
    },
    applyRead(conversationId: string, userId: string, messageIds: string[]) {
      const list = this.byConversation[conversationId] || [];
      list.forEach((message) => {
        if (messageIds.includes(message.id) && !message.read_by.includes(userId)) {
          message.read_by.push(userId);
        }
      });
    },
    setTyping(conversationId: string, userId: string, isTyping: boolean) {
      this.typing[conversationId] ||= {};
      this.typing[conversationId][userId] = isTyping;
    }
  }
});
