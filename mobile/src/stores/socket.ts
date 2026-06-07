import { defineStore } from 'pinia';
import { WS_BASE_URL } from '@/config/env';
import { useAuthStore } from '@/stores/auth';
import { useConversationsStore } from '@/stores/conversations';
import { useMessagesStore } from '@/stores/messages';
import type { Message } from '@/api/types';
import { initNotifications, notifyNewMessage } from '@/services/notifications';
import { activeConversationId } from '@/services/navigation';

interface SocketState {
  connected: boolean;
  socket: WebSocket | null;
  connecting: boolean;
  authenticated: boolean;
  authRequested: boolean;
  queue: Array<{ type: string; payload: Record<string, unknown> }>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function stringField(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return typeof value === 'string' ? value : null;
}

function stringArrayField(payload: Record<string, unknown>, key: string): string[] {
  const value = payload[key];
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

export const useSocketStore = defineStore('socket', {
  state: (): SocketState => ({
    connected: false,
    socket: null,
    connecting: false,
    authenticated: false,
    authRequested: false,
    queue: []
  }),
  actions: {
    sendAuth(socket: WebSocket, token: string) {
      if (this.authRequested || socket.readyState !== WebSocket.OPEN) return;
      this.authRequested = true;
      socket.send(JSON.stringify({ type: 'auth', payload: { token } }));
    },
    connect() {
      const auth = useAuthStore();
      auth.syncFromStorage();
      const accessToken = auth.accessToken;
      if (!accessToken) return;
      const existingSocket = this.socket;
      if (existingSocket?.readyState === WebSocket.OPEN) {
        if (this.authenticated) return;
        this.sendAuth(existingSocket, accessToken);
        return;
      }
      if (this.connecting || existingSocket?.readyState === WebSocket.CONNECTING) return;
      this.connecting = true;
      const socket = new WebSocket(`${WS_BASE_URL}/ws`);
      this.socket = socket;
      socket.onopen = () => {
        if (this.socket !== socket) return;
        this.sendAuth(socket, accessToken);
        void initNotifications();
      };
      socket.onclose = () => {
        if (this.socket !== socket) return;
        this.socket = null;
        this.connected = false;
        this.connecting = false;
        this.authenticated = false;
        this.authRequested = false;
      };
      socket.onerror = () => {
        if (this.socket !== socket) return;
        this.connected = false;
        this.connecting = false;
        this.authenticated = false;
        this.authRequested = false;
      };
      socket.onmessage = (event) => {
        if (this.socket !== socket) return;
        try {
          const message = JSON.parse(event.data) as unknown;
          if (!isRecord(message) || typeof message.type !== 'string') return;
          this.handle(message.type, message.payload);
        } catch {
          // Ignore malformed frames instead of breaking the connection handler.
        }
      };
    },
    disconnect() {
      this.socket?.close();
      this.socket = null;
      this.connected = false;
      this.connecting = false;
      this.authenticated = false;
      this.authRequested = false;
      this.queue = [];
    },
    canSendRealtime(): boolean {
      return this.socket?.readyState === WebSocket.OPEN && this.authenticated;
    },
    send(type: string, payload: Record<string, unknown>): boolean {
      const socket = this.socket;
      if (socket?.readyState === WebSocket.OPEN && this.authenticated) {
        socket.send(JSON.stringify({ type, payload }));
        return true;
      }
      this.queue.push({ type, payload });
      this.connect();
      return false;
    },
    sendNow(type: string, payload: Record<string, unknown>): boolean {
      const socket = this.socket;
      if (socket?.readyState === WebSocket.OPEN && this.authenticated) {
        socket.send(JSON.stringify({ type, payload }));
        return true;
      }
      this.connect();
      return false;
    },
    flushQueue() {
      const pending = [...this.queue];
      this.queue = [];
      pending.forEach((item) => this.send(item.type, item.payload));
    },
    join(conversationId: string) {
      this.send('conversation:join', { conversation_id: conversationId });
    },
    leave(conversationId: string) {
      this.send('conversation:leave', { conversation_id: conversationId });
    },
    handle(type: string, payload: unknown) {
      const messages = useMessagesStore();
      const conversations = useConversationsStore();
      if (!isRecord(payload)) return;
      if (type === 'auth:ok') {
        this.connected = true;
        this.connecting = false;
        this.authenticated = true;
        this.authRequested = false;
        this.flushQueue();
        return;
      }
      if (!this.authenticated) return;
      if (type === 'message:new') {
        const incoming = payload as unknown as Message;
        const auth = useAuthStore();
        const currentConversationId = activeConversationId();
        const isOwnMessage = incoming.sender_id === auth.user?.id;
        const isActiveConversation = incoming.conversation_id === currentConversationId;
        messages.upsert(incoming);
        if (!conversations.applyIncomingMessage(incoming, auth.user?.id, currentConversationId)) {
          void conversations.fetchAll();
        }
        if (!isOwnMessage && isActiveConversation) {
          messages.read(incoming.conversation_id);
          conversations.markRead(incoming.conversation_id);
        }
        if (!isOwnMessage && !isActiveConversation) {
          const conversation = conversations.items.find((item) => item.id === incoming.conversation_id);
          const sender = conversation?.participants.find((user) => user.id === incoming.sender_id);
          void notifyNewMessage(incoming, sender?.display_name || sender?.username || 'New message');
        }
      }
      if (type === 'message:deleted') messages.markDeleted(payload as unknown as Message);
      if (type === 'message:read') {
        const conversationId = stringField(payload, 'conversation_id');
        const userId = stringField(payload, 'user_id');
        if (conversationId && userId) messages.applyRead(conversationId, userId, stringArrayField(payload, 'message_ids'));
      }
      if (type === 'conversation:updated') {
        const conversationId = stringField(payload, 'conversation_id');
        if (conversationId && isRecord(payload.latest_message)) {
          conversations.applyLatest(conversationId, payload.latest_message as unknown as Message);
        }
      }
      if (type === 'user:online') {
        const userId = stringField(payload, 'user_id');
        if (userId) conversations.setUserPresence(userId, true);
      }
      if (type === 'user:offline') {
        const userId = stringField(payload, 'user_id');
        const lastSeenAt = stringField(payload, 'last_seen_at') || undefined;
        if (userId) conversations.setUserPresence(userId, false, lastSeenAt);
      }
      if (type === 'typing:update') {
        const conversationId = stringField(payload, 'conversation_id');
        const userId = stringField(payload, 'user_id');
        if (conversationId && userId && typeof payload.is_typing === 'boolean') {
          messages.setTyping(conversationId, userId, payload.is_typing);
        }
      }
    }
  }
});
