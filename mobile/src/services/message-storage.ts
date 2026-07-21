import type { Message } from '@/api/types';

const DATABASE_NAME = 'relay-message-storage';
const DATABASE_VERSION = 1;
const OUTBOX_STORE = 'outbox';
const CACHE_STORE = 'message-cache';

export interface StagedAttachment {
  name: string;
  type: string;
  lastModified: number;
  data: Blob;
}

export type OutboxState = 'queued' | 'sending' | 'failed';

export interface OutboxEntry {
  id: string;
  userId: string;
  conversationId: string;
  text: string | null;
  attachment: StagedAttachment | null;
  uploadedAttachmentIds: string[];
  createdAt: string;
  state: OutboxState;
  attemptCount: number;
  nextAttemptAt: number;
  lastError: string | null;
}

interface MessageCacheEntry {
  id: string;
  userId: string;
  conversationId: string;
  messages: Message[];
  updatedAt: number;
}

let databasePromise: Promise<IDBDatabase> | null = null;
const memoryOutbox = new Map<string, OutboxEntry>();
const memoryCache = new Map<string, MessageCacheEntry>();

function cacheId(userId: string, conversationId: string) {
  return `${userId}:${conversationId}`;
}

function openDatabase(): Promise<IDBDatabase> | null {
  if (typeof indexedDB === 'undefined') return null;
  if (databasePromise) return databasePromise;
  databasePromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(OUTBOX_STORE)) {
        const store = database.createObjectStore(OUTBOX_STORE, { keyPath: 'id' });
        store.createIndex('userId', 'userId');
      }
      if (!database.objectStoreNames.contains(CACHE_STORE)) {
        const store = database.createObjectStore(CACHE_STORE, { keyPath: 'id' });
        store.createIndex('userId', 'userId');
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error('Local message database upgrade is blocked'));
  });
  return databasePromise;
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function write(storeName: string, value: unknown): Promise<void> {
  const database = await openDatabase();
  if (!database) return;
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(storeName, 'readwrite');
    transaction.objectStore(storeName).put(value);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error);
  });
}

async function remove(storeName: string, key: IDBValidKey): Promise<void> {
  const database = await openDatabase();
  if (!database) return;
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(storeName, 'readwrite');
    transaction.objectStore(storeName).delete(key);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error);
  });
}

async function recordsForUser<T>(storeName: string, userId: string): Promise<T[]> {
  const database = await openDatabase();
  if (!database) return [];
  const transaction = database.transaction(storeName, 'readonly');
  return requestResult(transaction.objectStore(storeName).index('userId').getAll(userId)) as Promise<T[]>;
}

export async function saveOutboxEntry(entry: OutboxEntry): Promise<void> {
  memoryOutbox.set(entry.id, entry);
  await write(OUTBOX_STORE, entry);
}

export async function deleteOutboxEntry(id: string): Promise<void> {
  memoryOutbox.delete(id);
  await remove(OUTBOX_STORE, id);
}

export async function loadOutbox(userId: string): Promise<OutboxEntry[]> {
  const databaseEntries = await recordsForUser<OutboxEntry>(OUTBOX_STORE, userId);
  const entries = databaseEntries.length
    ? databaseEntries
    : [...memoryOutbox.values()].filter((entry) => entry.userId === userId);
  entries.forEach((entry) => memoryOutbox.set(entry.id, entry));
  return entries.sort((left, right) => left.createdAt.localeCompare(right.createdAt));
}

export async function saveMessageCache(
  userId: string,
  conversationId: string,
  messages: Message[]
): Promise<void> {
  const entry: MessageCacheEntry = {
    id: cacheId(userId, conversationId),
    userId,
    conversationId,
    messages: messages.filter((message) => !message.delivery_state).slice(-200),
    updatedAt: Date.now()
  };
  memoryCache.set(entry.id, entry);
  await write(CACHE_STORE, entry);
}

export async function loadMessageCache(
  userId: string,
  conversationId: string
): Promise<Message[]> {
  const id = cacheId(userId, conversationId);
  const database = await openDatabase();
  if (!database) return memoryCache.get(id)?.messages || [];
  const transaction = database.transaction(CACHE_STORE, 'readonly');
  const entry = await requestResult(
    transaction.objectStore(CACHE_STORE).get(id)
  ) as MessageCacheEntry | undefined;
  if (entry) memoryCache.set(id, entry);
  return entry?.messages || [];
}

export async function clearUserMessageStorage(userId: string): Promise<void> {
  const outbox = await loadOutbox(userId);
  const cache = await recordsForUser<MessageCacheEntry>(CACHE_STORE, userId);
  await Promise.all([
    ...outbox.map((entry) => deleteOutboxEntry(entry.id)),
    ...cache.map((entry) => remove(CACHE_STORE, entry.id))
  ]);
  for (const [id, entry] of memoryCache) {
    if (entry.userId === userId) memoryCache.delete(id);
  }
}
