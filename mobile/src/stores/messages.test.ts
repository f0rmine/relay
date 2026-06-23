import { createPinia, setActivePinia } from 'pinia';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Message } from '@/api/types';
import { useMessagesStore } from './messages';

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ user: { id: 'sender-1' } })
}));

vi.mock('@/i18n', () => ({
  translate: (key: string) => key
}));

vi.mock('@/stores/socket', () => ({
  useSocketStore: () => ({
    sendNow: () => true,
    send: () => true
  })
}));

function serverMessage(requestId: string): Message {
  return {
    id: 'message-1',
    conversation_id: 'conversation-1',
    sender_id: 'sender-1',
    text: 'hello',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    attachments: [],
    read_by: [],
    request_id: requestId
  };
}

describe('messages store optimistic reconciliation', () => {
  beforeEach(() => setActivePinia(createPinia()));
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('replaces the exact pending message acknowledged by the server', () => {
    const store = useMessagesStore();
    store.addOptimistic('conversation-1', 'sender-1', 'hello', [], 'request-1');
    store.addOptimistic('conversation-1', 'sender-1', 'hello', [], 'request-2');

    store.upsert(serverMessage('request-2'));

    expect(
      store.byConversation['conversation-1'].map((message) => message.id).sort()
    ).toEqual(['message-1', 'pending-request-1']);
  });

  it('removes a rejected pending message and returns its conversation', () => {
    const store = useMessagesStore();
    store.addOptimistic('conversation-1', 'sender-1', 'hello', [], 'request-1');

    expect(store.failPending('request-1')).toBe('conversation-1');
    expect(store.byConversation['conversation-1']).toEqual([]);
  });

  it('expires a pending message when no server acknowledgement arrives', () => {
    vi.useFakeTimers();
    const dispatchEvent = vi.fn();
    vi.stubGlobal('window', { dispatchEvent });
    const store = useMessagesStore();
    store.addOptimistic('conversation-1', 'sender-1', 'hello', [], 'request-1');

    vi.advanceTimersByTime(15000);

    expect(store.byConversation['conversation-1']).toEqual([]);
    expect(dispatchEvent).toHaveBeenCalledOnce();
  });
});
