import { createPinia, setActivePinia } from 'pinia';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Message } from '@/api/types';
import type { OutboxEntry } from '@/services/message-storage';
import { useMessagesStore } from './messages';

const mocks = vi.hoisted(() => ({
  apiFetch: vi.fn(),
  saveOutboxEntry: vi.fn(async () => undefined),
  deleteOutboxEntry: vi.fn(async () => undefined),
  loadOutbox: vi.fn<() => Promise<OutboxEntry[]>>(async () => []),
  saveMessageCache: vi.fn(async () => undefined),
  loadMessageCache: vi.fn(async () => [])
}));

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ user: { id: 'sender-1' } })
}));

vi.mock('@/stores/socket', () => ({
  useSocketStore: () => ({ send: () => true })
}));

vi.mock('@/services/message-storage', () => ({
  saveOutboxEntry: mocks.saveOutboxEntry,
  deleteOutboxEntry: mocks.deleteOutboxEntry,
  loadOutbox: mocks.loadOutbox,
  saveMessageCache: mocks.saveMessageCache,
  loadMessageCache: mocks.loadMessageCache
}));

vi.mock('@/api/client', () => {
  class ApiError extends Error {
    constructor(public status: number, message: string) {
      super(message);
    }
  }
  return { ApiError, apiFetch: mocks.apiFetch };
});

function serverMessage(clientMessageId: string): Message {
  return {
    id: 'message-1',
    client_message_id: clientMessageId,
    conversation_id: 'conversation-1',
    sender_id: 'sender-1',
    text: 'hello',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    attachments: [],
    read_by: []
  };
}

describe('durable message outbox', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.stubGlobal('navigator', { onLine: false });
    vi.stubGlobal('crypto', { randomUUID: () => 'client-message-1' });
    mocks.apiFetch.mockReset();
    mocks.saveOutboxEntry.mockClear();
    mocks.deleteOutboxEntry.mockClear();
    mocks.loadOutbox.mockReset();
    mocks.loadOutbox.mockResolvedValue([]);
    useMessagesStore().reset();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('persists and displays a message before attempting delivery', async () => {
    const store = useMessagesStore();

    await store.enqueue('conversation-1', ' hello ');

    expect(mocks.saveOutboxEntry).toHaveBeenCalled();
    expect(store.byConversation['conversation-1'][0]).toMatchObject({
      client_message_id: 'client-message-1',
      text: 'hello',
      delivery_state: 'queued'
    });
    expect(mocks.apiFetch).not.toHaveBeenCalled();
  });

  it('delivers the same client id and removes the durable entry after acknowledgement', async () => {
    const store = useMessagesStore();
    await store.enqueue('conversation-1', 'hello');
    vi.stubGlobal('navigator', { onLine: true });
    mocks.apiFetch.mockResolvedValue(serverMessage('client-message-1'));

    await store.flushOutbox();

    const request = JSON.parse(mocks.apiFetch.mock.calls[0][1].body as string);
    expect(request.client_message_id).toBe('client-message-1');
    expect(mocks.deleteOutboxEntry).toHaveBeenCalledWith('client-message-1');
    expect(store.byConversation['conversation-1']).toEqual([
      expect.objectContaining({ id: 'message-1', delivery_state: undefined })
    ]);
  });

  it('keeps a permanently rejected message visible until manual retry', async () => {
    const { ApiError } = await import('@/api/client');
    const store = useMessagesStore();
    await store.enqueue('conversation-1', 'hello');
    vi.stubGlobal('navigator', { onLine: true });
    mocks.apiFetch.mockRejectedValueOnce(new ApiError(400, 'invalid'));

    await store.flushOutbox();

    expect(store.byConversation['conversation-1'][0].delivery_state).toBe('failed');

    mocks.apiFetch.mockResolvedValueOnce(serverMessage('client-message-1'));
    await store.retry('client-message-1');
    expect(store.byConversation['conversation-1'][0].id).toBe('message-1');
  });

  it('restores queued records after an app restart', async () => {
    mocks.loadOutbox.mockResolvedValueOnce([{
      id: 'restored-1',
      userId: 'sender-1',
      conversationId: 'conversation-1',
      text: 'offline message',
      attachment: null,
      uploadedAttachmentIds: [],
      createdAt: new Date().toISOString(),
      state: 'queued',
      attemptCount: 1,
      nextAttemptAt: 0,
      lastError: null
    }]);
    const store = useMessagesStore();

    await store.restoreLocal('sender-1');

    expect(store.byConversation['conversation-1'][0]).toMatchObject({
      client_message_id: 'restored-1',
      delivery_state: 'queued'
    });
  });

  it('does not overtake an earlier transient failure in the same conversation', async () => {
    const ids = ['client-message-1', 'client-message-2'];
    vi.stubGlobal('crypto', { randomUUID: () => ids.shift()! });
    const { ApiError } = await import('@/api/client');
    const store = useMessagesStore();
    await store.enqueue('conversation-1', 'first');
    await store.enqueue('conversation-1', 'second');
    vi.stubGlobal('navigator', { onLine: true });
    mocks.apiFetch.mockRejectedValueOnce(new ApiError(503, 'offline'));

    await store.flushOutbox();

    expect(mocks.apiFetch).toHaveBeenCalledTimes(1);
    expect(store.outbox['client-message-1'].state).toBe('queued');
    expect(store.outbox['client-message-2'].state).toBe('queued');
  });
});
