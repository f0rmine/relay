import { defineStore } from 'pinia';
import { apiFetch } from '@/api/client';
import type { Conversation, Message, User } from '@/api/types';

interface ConversationState {
  items: Conversation[];
  loading: boolean;
}

export const useConversationsStore = defineStore('conversations', {
  state: (): ConversationState => ({
    items: [],
    loading: false
  }),
  actions: {
    reset() {
      this.items = [];
      this.loading = false;
    },
    async fetchAll() {
      this.loading = true;
      try {
        this.items = await apiFetch<Conversation[]>('/conversations');
      } finally {
        this.loading = false;
      }
    },
    async start(participantId: string): Promise<Conversation> {
      const conversation = await apiFetch<Conversation>('/conversations', {
        method: 'POST',
        body: JSON.stringify({ participant_id: participantId })
      });
      this.upsert(conversation);
      return conversation;
    },
    upsert(conversation: Conversation) {
      const index = this.items.findIndex((item) => item.id === conversation.id);
      if (index >= 0) this.items[index] = conversation;
      else this.items.unshift(conversation);
      this.sort();
    },
    applyLatest(conversationId: string, latestMessage: Message) {
      const item = this.items.find((conversation) => conversation.id === conversationId);
      if (!item) return;
      item.latest_message = latestMessage;
      item.updated_at = latestMessage.created_at;
      this.sort();
    },
    applyIncomingMessage(message: Message, currentUserId?: string, activeConversationId?: string) {
      const item = this.items.find((conversation) => conversation.id === message.conversation_id);
      if (!item) return false;
      item.latest_message = message;
      item.updated_at = message.created_at;
      if (message.sender_id !== currentUserId && message.conversation_id !== activeConversationId) {
        item.unread_count += 1;
      }
      if (message.conversation_id === activeConversationId) {
        item.unread_count = 0;
      }
      this.sort();
      return true;
    },
    setUserPresence(userId: string, online: boolean, lastSeen?: string) {
      this.items.forEach((conversation) => {
        conversation.participants.forEach((user) => {
          if (user.id === userId) {
            user.is_online = online;
            if (lastSeen) user.last_seen_at = lastSeen;
          }
        });
      });
    },
    markRead(conversationId: string) {
      const item = this.items.find((conversation) => conversation.id === conversationId);
      if (item) item.unread_count = 0;
    },
    otherParticipant(conversation: Conversation, currentUserId?: string): User | undefined {
      return conversation.participants.find((participant) => participant.id !== currentUserId);
    },
    sort() {
      this.items.sort((a, b) => +new Date(b.updated_at) - +new Date(a.updated_at));
    }
  }
});
