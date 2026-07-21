import 'fake-indexeddb/auto';
import { afterEach, describe, expect, it } from 'vitest';
import type { Message } from '@/api/types';
import {
  clearUserMessageStorage,
  loadMessageCache,
  loadOutbox,
  saveMessageCache,
  saveOutboxEntry,
  type OutboxEntry
} from './message-storage';

const userId = 'storage-test-user';

function outboxEntry(): OutboxEntry {
  return {
    id: 'outbox-1',
    userId,
    conversationId: 'conversation-1',
    text: 'offline',
    attachment: {
      name: 'note.txt',
      type: 'text/plain',
      lastModified: 123,
      data: new Blob(['attachment body'], { type: 'text/plain' })
    },
    uploadedAttachmentIds: [],
    createdAt: new Date().toISOString(),
    state: 'queued',
    attemptCount: 0,
    nextAttemptAt: 0,
    lastError: null
  };
}

function message(id: string, deliveryState?: Message['delivery_state']): Message {
  return {
    id,
    conversation_id: 'conversation-1',
    sender_id: userId,
    text: id,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    attachments: [],
    read_by: [],
    delivery_state: deliveryState
  };
}

describe('IndexedDB message storage', () => {
  afterEach(async () => clearUserMessageStorage(userId));

  it('persists queued messages and attachment bytes', async () => {
    await saveOutboxEntry(outboxEntry());

    const restored = await loadOutbox(userId);

    expect(restored).toHaveLength(1);
    expect(restored[0].text).toBe('offline');
    expect(await restored[0].attachment?.data.text()).toBe('attachment body');
  });

  it('caches confirmed history without duplicating local outbox messages', async () => {
    await saveMessageCache(userId, 'conversation-1', [
      message('server-1'),
      message('pending-1', 'queued')
    ]);

    const restored = await loadMessageCache(userId, 'conversation-1');

    expect(restored.map((item) => item.id)).toEqual(['server-1']);
  });
});
