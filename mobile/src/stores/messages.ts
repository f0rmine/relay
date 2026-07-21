import { defineStore } from 'pinia';
import { ApiError, apiFetch } from '@/api/client';
import type { Attachment, Message } from '@/api/types';
import { useAuthStore } from '@/stores/auth';
import { useSocketStore } from '@/stores/socket';
import {
  deleteOutboxEntry,
  loadMessageCache,
  loadOutbox,
  saveMessageCache,
  saveOutboxEntry,
  type OutboxEntry
} from '@/services/message-storage';

interface MessagesState {
  byConversation: Record<string, Message[]>;
  cursors: Record<string, string | null>;
  hasMore: Record<string, boolean>;
  typing: Record<string, Record<string, boolean>>;
  outbox: Record<string, OutboxEntry>;
  restoredUserId: string | null;
  loading: boolean;
}

const previewUrls = new Map<string, string>();
let flushPromise: Promise<void> | null = null;
let retryTimer: ReturnType<typeof setTimeout> | null = null;
let retryAt = 0;
let lifecycleEpoch = 0;

function nextBackoff(attemptCount: number) {
  const base = Math.min(1000 * 2 ** Math.max(0, attemptCount - 1), 30000);
  return base + Math.floor(Math.random() * Math.max(250, base * 0.25));
}

function isPermanentFailure(error: unknown) {
  if (!(error instanceof ApiError) || error.status < 400 || error.status >= 500) return false;
  return ![401, 408, 409, 425, 429].includes(error.status);
}

function releasePreview(id: string) {
  const url = previewUrls.get(id);
  if (url) URL.revokeObjectURL(url);
  previewUrls.delete(id);
}

function localAttachments(entry: OutboxEntry): Attachment[] {
  if (!entry.attachment) return [];
  releasePreview(entry.id);
  const publicUrl = URL.createObjectURL(entry.attachment.data);
  previewUrls.set(entry.id, publicUrl);
  return [{
    id: `local-attachment-${entry.id}`,
    uploader_id: entry.userId,
    original_filename: entry.attachment.name,
    mime_type: entry.attachment.type,
    file_size: entry.attachment.data.size,
    public_url: publicUrl,
    created_at: entry.createdAt
  }];
}

function localMessage(entry: OutboxEntry): Message {
  return {
    id: `pending-${entry.id}`,
    client_message_id: entry.id,
    conversation_id: entry.conversationId,
    sender_id: entry.userId,
    text: entry.text,
    created_at: entry.createdAt,
    updated_at: entry.createdAt,
    edited_at: null,
    deleted_at: null,
    deleted_by_id: null,
    attachments: localAttachments(entry),
    read_by: [],
    request_id: entry.id,
    delivery_state: entry.state
  };
}

export const useMessagesStore = defineStore('messages', {
  state: (): MessagesState => ({
    byConversation: {},
    cursors: {},
    hasMore: {},
    typing: {},
    outbox: {},
    restoredUserId: null,
    loading: false
  }),
  actions: {
    reset() {
      lifecycleEpoch += 1;
      if (retryTimer) clearTimeout(retryTimer);
      retryTimer = null;
      retryAt = 0;
      previewUrls.forEach((url) => URL.revokeObjectURL(url));
      previewUrls.clear();
      this.byConversation = {};
      this.cursors = {};
      this.hasMore = {};
      this.typing = {};
      this.outbox = {};
      this.restoredUserId = null;
      this.loading = false;
    },
    async restoreLocal(userId: string) {
      if (this.restoredUserId === userId) return;
      const entries = await loadOutbox(userId);
      this.restoredUserId = userId;
      for (const entry of entries) {
        if (entry.state === 'sending') entry.state = 'queued';
        this.outbox[entry.id] = entry;
        this.putLocalMessage(entry);
      }
    },
    async restoreConversation(conversationId: string) {
      const auth = useAuthStore();
      if (!auth.user) return;
      await this.restoreLocal(auth.user.id);
      if (this.byConversation[conversationId]?.some((message) => !message.delivery_state)) return;
      const cached = await loadMessageCache(auth.user.id, conversationId);
      if (!cached.length) return;
      const local = (this.byConversation[conversationId] || []).filter(
        (message) => Boolean(message.delivery_state)
      );
      this.byConversation[conversationId] = [...cached, ...local];
    },
    async fetch(conversationId: string, older = false) {
      await this.restoreConversation(conversationId);
      this.loading = true;
      try {
        const cursor = older ? this.cursors[conversationId] : null;
        const params = cursor ? `?cursor=${encodeURIComponent(cursor)}` : '';
        const response = await apiFetch<{
          items: Message[];
          next_cursor: string | null;
          has_more: boolean;
        }>(`/conversations/${conversationId}/messages${params}`);
        const ascending = response.items.reverse();
        const local = (this.byConversation[conversationId] || []).filter(
          (message) => Boolean(message.delivery_state)
        );
        this.byConversation[conversationId] = older
          ? [...ascending, ...(this.byConversation[conversationId] || [])]
          : [...ascending, ...local];
        this.cursors[conversationId] = response.next_cursor;
        this.hasMore[conversationId] = response.has_more;
        this.persistConversation(conversationId);
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
    async enqueue(conversationId: string, text: string, file: File | null = null) {
      const auth = useAuthStore();
      if (!auth.user) throw new Error('Authentication is required');
      const cleanText = text.trim();
      if (!cleanText && !file) throw new Error('Message text or attachment is required');
      const id = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
      const entry: OutboxEntry = {
        id,
        userId: auth.user.id,
        conversationId,
        text: cleanText || null,
        attachment: file ? {
          name: file.name,
          type: file.type,
          lastModified: file.lastModified,
          data: file
        } : null,
        uploadedAttachmentIds: [],
        createdAt: new Date().toISOString(),
        state: 'queued',
        attemptCount: 0,
        nextAttemptAt: 0,
        lastError: null
      };
      await saveOutboxEntry(entry);
      this.outbox[id] = entry;
      this.putLocalMessage(entry);
      void this.flushOutbox();
      return id;
    },
    putLocalMessage(entry: OutboxEntry) {
      const list = this.byConversation[entry.conversationId] || [];
      const message = localMessage(entry);
      const index = list.findIndex((item) => item.client_message_id === entry.id);
      if (index >= 0) list[index] = message;
      else list.push(message);
      this.sortMessages(list);
      this.byConversation[entry.conversationId] = list;
    },
    scheduleFlush(timestamp: number) {
      if (retryTimer && retryAt <= timestamp) return;
      if (retryTimer) clearTimeout(retryTimer);
      const delay = Math.max(0, timestamp - Date.now());
      retryAt = timestamp;
      retryTimer = setTimeout(() => {
        retryTimer = null;
        retryAt = 0;
        void this.flushOutbox();
      }, delay);
    },
    async deliverOutboxEntry(
      entry: OutboxEntry,
      userId: string,
      epoch: number
    ): Promise<'delivered' | 'permanent' | 'transient' | 'stale'> {
      entry.state = 'sending';
      entry.attemptCount += 1;
      entry.lastError = null;
      await saveOutboxEntry(entry);
      this.putLocalMessage(entry);
      try {
        if (entry.attachment && !entry.uploadedAttachmentIds.length) {
          const file = new File(
            [entry.attachment.data],
            entry.attachment.name,
            { type: entry.attachment.type, lastModified: entry.attachment.lastModified }
          );
          const attachment = await this.upload(file, entry.conversationId);
          if (epoch !== lifecycleEpoch || useAuthStore().user?.id !== userId) return 'stale';
          entry.uploadedAttachmentIds = [attachment.id];
          await saveOutboxEntry(entry);
        }
        const message = await apiFetch<Message>('/messages', {
          method: 'POST',
          body: JSON.stringify({
            client_message_id: entry.id,
            conversation_id: entry.conversationId,
            text: entry.text,
            attachment_ids: entry.uploadedAttachmentIds
          })
        });
        if (epoch !== lifecycleEpoch || useAuthStore().user?.id !== userId) return 'stale';
        await this.acknowledge(message);
        return 'delivered';
      } catch (error) {
        if (epoch !== lifecycleEpoch || useAuthStore().user?.id !== userId) return 'stale';
        const permanent = isPermanentFailure(error);
        entry.state = permanent ? 'failed' : 'queued';
        entry.lastError = error instanceof Error ? error.message : String(error);
        entry.nextAttemptAt = permanent ? 0 : Date.now() + nextBackoff(entry.attemptCount);
        await saveOutboxEntry(entry);
        this.putLocalMessage(entry);
        if (!permanent) this.scheduleFlush(entry.nextAttemptAt);
        return permanent ? 'permanent' : 'transient';
      }
    },
    async flushOutbox() {
      if (flushPromise) return flushPromise;
      const auth = useAuthStore();
      if (!auth.user || (typeof navigator !== 'undefined' && !navigator.onLine)) return;
      const userId = auth.user.id;
      const epoch = lifecycleEpoch;
      flushPromise = (async () => {
        await this.restoreLocal(userId);
        const entries = Object.values(this.outbox)
          .filter((entry) => entry.userId === userId && entry.state !== 'failed')
          .sort((left, right) => left.createdAt.localeCompare(right.createdAt));
        const grouped = new Map<string, OutboxEntry[]>();
        for (const entry of entries) {
          const queue = grouped.get(entry.conversationId) || [];
          queue.push(entry);
          grouped.set(entry.conversationId, queue);
        }
        const queues = [...grouped.values()];
        let queueIndex = 0;
        const worker = async () => {
          while (queueIndex < queues.length) {
            const queue = queues[queueIndex++];
            for (const entry of queue) {
              if (entry.nextAttemptAt > Date.now()) {
                this.scheduleFlush(entry.nextAttemptAt);
                break;
              }
              const result = await this.deliverOutboxEntry(entry, userId, epoch);
              if (result === 'transient' || result === 'stale') break;
            }
          }
        };
        await Promise.all(
          Array.from({ length: Math.min(3, queues.length) }, () => worker())
        );
      })().finally(() => {
        flushPromise = null;
      });
      return flushPromise;
    },
    async retry(clientMessageId: string) {
      const entry = this.outbox[clientMessageId];
      if (!entry) return;
      entry.state = 'queued';
      entry.nextAttemptAt = 0;
      entry.lastError = null;
      await saveOutboxEntry(entry);
      this.putLocalMessage(entry);
      await this.flushOutbox();
    },
    async removePending(clientMessageId: string) {
      const entry = this.outbox[clientMessageId];
      if (!entry) return;
      delete this.outbox[clientMessageId];
      releasePreview(clientMessageId);
      await deleteOutboxEntry(clientMessageId);
      const list = this.byConversation[entry.conversationId] || [];
      this.byConversation[entry.conversationId] = list.filter(
        (message) => message.client_message_id !== clientMessageId
      );
    },
    async acknowledge(message: Message) {
      const clientMessageId = message.client_message_id || message.request_id;
      if (clientMessageId && this.outbox[clientMessageId]) {
        const entry = this.outbox[clientMessageId];
        delete this.outbox[clientMessageId];
        releasePreview(clientMessageId);
        await deleteOutboxEntry(clientMessageId);
        const list = this.byConversation[entry.conversationId] || [];
        this.byConversation[entry.conversationId] = list.filter(
          (item) => item.client_message_id !== clientMessageId
        );
      }
      this.upsert(message);
    },
    read(conversationId: string) {
      useSocketStore().send('message:read', { conversation_id: conversationId });
    },
    async delete(messageId: string) {
      const message = await apiFetch<Message>(`/messages/${messageId}`, { method: 'DELETE' });
      this.markDeleted(message);
    },
    upsert(message: Message) {
      const clientMessageId = message.client_message_id || message.request_id;
      if (clientMessageId && this.outbox[clientMessageId]) {
        const entry = this.outbox[clientMessageId];
        delete this.outbox[clientMessageId];
        releasePreview(clientMessageId);
        void deleteOutboxEntry(clientMessageId);
        const pending = this.byConversation[entry.conversationId] || [];
        this.byConversation[entry.conversationId] = pending.filter(
          (item) => item.client_message_id !== clientMessageId
        );
      }
      const list = this.byConversation[message.conversation_id] || [];
      const index = list.findIndex((item) => item.id === message.id);
      if (index >= 0) list[index] = { ...message, delivery_state: undefined };
      else list.push({ ...message, delivery_state: undefined });
      this.sortMessages(list);
      this.byConversation[message.conversation_id] = list;
      this.persistConversation(message.conversation_id);
    },
    failPending(clientMessageId: string): string | undefined {
      const entry = this.outbox[clientMessageId];
      if (!entry) return undefined;
      entry.state = 'failed';
      entry.lastError = 'Server rejected the message';
      void saveOutboxEntry(entry);
      this.putLocalMessage(entry);
      return entry.conversationId;
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
      this.persistConversation(conversationId);
    },
    setTyping(conversationId: string, userId: string, isTyping: boolean) {
      this.typing[conversationId] ||= {};
      this.typing[conversationId][userId] = isTyping;
    },
    sortMessages(messages: Message[]) {
      messages.sort((left, right) => {
        const timeDelta = +new Date(left.created_at) - +new Date(right.created_at);
        if (timeDelta !== 0) return timeDelta;
        return left.id.localeCompare(right.id);
      });
    },
    persistConversation(conversationId: string) {
      const auth = useAuthStore();
      if (!auth.user) return;
      void saveMessageCache(
        auth.user.id,
        conversationId,
        this.byConversation[conversationId] || []
      );
    }
  }
});
