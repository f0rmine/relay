import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Message } from '@/api/types';

const SECRET = 'meet at the usual place';

const mocks = vi.hoisted(() => ({
  apiFetch: vi.fn(),
  encryptForConversation: vi.fn(),
  invalidateKeys: vi.fn(),
  savePlaintext: vi.fn(async () => undefined),
  conversation: {
    id: 'secure-1',
    e2ee: true,
    participants: [{ id: 'me' }, { id: 'bob' }]
  }
}));

vi.mock('@/api/client', () => {
  class ApiError extends Error {
    constructor(public status: number, message: string) {
      super(message);
    }
  }
  return { ApiError, apiFetch: mocks.apiFetch };
});
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { id: 'me' } }) }));
vi.mock('@/stores/socket', () => ({ useSocketStore: () => ({ send: () => true }) }));
vi.mock('@/i18n', () => ({ translate: (key: string) => key }));
vi.mock('@/stores/conversations', () => ({
  useConversationsStore: () => ({
    items: [mocks.conversation],
    applyConversationInfo: () => undefined
  })
}));
vi.mock('@/stores/e2ee', () => {
  class E2eeError extends Error {
    constructor(public code: string) {
      super(code);
    }
  }
  return {
    E2eeError,
    useE2eeStore: () => ({
      encryptForConversation: mocks.encryptForConversation,
      invalidateKeys: mocks.invalidateKeys,
      decryptMessage: async (message: Message) => message
    })
  };
});
vi.mock('@/services/message-storage', () => ({
  saveOutboxEntry: vi.fn(async () => undefined),
  deleteOutboxEntry: vi.fn(async () => undefined),
  loadOutbox: vi.fn(async () => []),
  saveMessageCache: vi.fn(async () => undefined),
  loadMessageCache: vi.fn(async () => []),
  savePlaintext: mocks.savePlaintext
}));

import { ApiError } from '@/api/client';
import { E2eeError } from '@/stores/e2ee';
import { useMessagesStore } from './messages';

const ApiErrorCtor = ApiError as unknown as new (status: number, message: string) => Error;
const E2eeErrorCtor = E2eeError as unknown as new (code: string) => Error;

function serverMessage(clientMessageId = 'x'): Message {
  return {
    id: 'm1',
    conversation_id: 'secure-1',
    sender_id: 'me',
    client_message_id: clientMessageId,
    text: null,
    e2ee: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    attachments: [],
    read_by: []
  };
}

/** The real server echoes the client_message_id it was sent. */
async function echo(_path: string, init?: RequestInit): Promise<Message> {
  return serverMessage(JSON.parse(String(init?.body)).client_message_id);
}

function bodies(): string[] {
  return mocks.apiFetch.mock.calls.map(([, init]) => String((init as RequestInit | undefined)?.body ?? ''));
}

describe('encrypted sending', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    mocks.apiFetch.mockReset();
    mocks.encryptForConversation.mockReset();
    mocks.invalidateKeys.mockReset();
    mocks.savePlaintext.mockClear();
    vi.stubGlobal('navigator', { onLine: true });
    mocks.encryptForConversation.mockResolvedValue({
      envelopes: [{ user_id: 'bob', device_id: 'bob-phone', ciphertext: 'opaque' }],
      sender_device_id: 'my-phone'
    });
  });

  it('sends envelopes only, never the plaintext, and keeps the text locally', async () => {
    mocks.apiFetch.mockImplementation(echo);
    const store = useMessagesStore();
    await store.enqueue('secure-1', SECRET);
    await store.flushOutbox();

    expect(mocks.encryptForConversation).toHaveBeenCalledTimes(1);
    expect(mocks.encryptForConversation).toHaveBeenCalledWith(
      mocks.conversation,
      { v: 1, text: SECRET, reply_to_id: null },
      false
    );
    const sent = JSON.parse(bodies()[0]);
    expect(sent).toMatchObject({ envelopes: [{ device_id: 'bob-phone' }], sender_device_id: 'my-phone' });
    expect(sent.text).toBeUndefined();
    expect(bodies().join('')).not.toContain(SECRET);
    expect(mocks.savePlaintext).toHaveBeenCalledWith('me', 'secure-1', 'm1', { text: SECRET, reply_to_id: null });
    expect(store.byConversation['secure-1'].find((m) => m.id === 'm1')?.text).toBe(SECRET);
    expect(Object.keys(store.outbox)).toHaveLength(0);
  });

  it('re-encrypts with fresh keys after a device-list mismatch', async () => {
    mocks.apiFetch
      .mockRejectedValueOnce(new ApiErrorCtor(409, 'device_mismatch'))
      .mockImplementationOnce(echo);
    const store = useMessagesStore();
    await store.enqueue('secure-1', SECRET);
    await store.flushOutbox();
    expect(mocks.invalidateKeys).toHaveBeenCalled();
    expect(mocks.encryptForConversation.mock.calls.map((call) => call[2])).toEqual([false, true]);
    expect(bodies().join('')).not.toContain(SECRET);
  });

  it('fails permanently (no plaintext fallback) when the safety number changed', async () => {
    mocks.encryptForConversation.mockRejectedValue(new E2eeErrorCtor('safety-number-changed'));
    const store = useMessagesStore();
    const id = await store.enqueue('secure-1', SECRET);
    await store.flushOutbox();
    expect(mocks.apiFetch).not.toHaveBeenCalled();
    expect(store.outbox[id].state).toBe('failed');
  });

  it('refuses attachments before uploading anything', async () => {
    const store = useMessagesStore();
    const id = await store.enqueue('secure-1', '', new File(['x'], 'photo.png', { type: 'image/png' }));
    await store.flushOutbox();
    expect(mocks.apiFetch).not.toHaveBeenCalled();
    expect(store.outbox[id].state).toBe('failed');
  });

  it('refuses to edit an encrypted message without contacting the server', async () => {
    const store = useMessagesStore();
    store.upsert({ ...serverMessage(), text: SECRET });
    await expect(store.edit('m1', 'new secret')).rejects.toThrow();
    expect(mocks.apiFetch).not.toHaveBeenCalled();
  });

  it('keeps decrypted text when a server event without text arrives', () => {
    const store = useMessagesStore();
    store.upsert({ ...serverMessage(), text: SECRET });
    store.upsert({ ...serverMessage(), reactions: [{ emoji: '👍', user_ids: ['bob'] }] });
    expect(store.byConversation['secure-1'][0].text).toBe(SECRET);
  });
});
