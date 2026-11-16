import type { Message } from '@/api/types';

const DATABASE_NAME = 'relay-message-storage';
const DATABASE_VERSION = 2;
const OUTBOX_STORE = 'outbox';
const CACHE_STORE = 'message-cache';
/** Decrypted E2EE messages. The only copy: ratchet keys are single-use. */
const PLAINTEXT_STORE = 'e2ee-plaintext';

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
  reply_to_id?: string | null;
  scheduled_at?: string | null;
  mentions?: string[];
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

export interface E2eePlaintext {
  text: string;
  reply_to_id?: string | null;
}

interface PlaintextEntry {
  id: string;
  userId: string;
  conversationId: string;
  messageId: string;
  payload: E2eePlaintext;
  savedAt: number;
}

let databasePromise: Promise<IDBDatabase> | null = null;
const memoryPlaintext = new Map<string, PlaintextEntry>();
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
      if (!database.objectStoreNames.contains(PLAINTEXT_STORE)) {
        const store = database.createObjectStore(PLAINTEXT_STORE, { keyPath: 'id' });
        store.createIndex('userId', 'userId');
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => {
      databasePromise = null;
      reject(request.error);
    };
    request.onblocked = () => {
      databasePromise = null;
      reject(new Error('Local message database upgrade is blocked'));
    };
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

const plaintextId = (userId: string, messageId: string) => `${userId}:${messageId}`;

export async function savePlaintext(
  userId: string,
  conversationId: string,
  messageId: string,
  payload: E2eePlaintext
): Promise<void> {
  const entry: PlaintextEntry = {
    id: plaintextId(userId, messageId),
    userId,
    conversationId,
    messageId,
    payload,
    savedAt: Date.now()
  };
  memoryPlaintext.set(entry.id, entry);
  await write(PLAINTEXT_STORE, entry);
}

export async function loadPlaintext(userId: string, messageId: string): Promise<E2eePlaintext | null> {
  const id = plaintextId(userId, messageId);
  const cached = memoryPlaintext.get(id);
  if (cached) return cached.payload;
  const database = await openDatabase();
  if (!database) return null;
  const transaction = database.transaction(PLAINTEXT_STORE, 'readonly');
  const entry = await requestResult(
    transaction.objectStore(PLAINTEXT_STORE).get(id)
  ) as PlaintextEntry | undefined;
  if (entry) memoryPlaintext.set(id, entry);
  return entry?.payload ?? null;
}

export async function clearUserMessageStorage(userId: string): Promise<void> {
  const outbox = await loadOutbox(userId);
  const cache = await recordsForUser<MessageCacheEntry>(CACHE_STORE, userId);
  const plaintext = await recordsForUser<PlaintextEntry>(PLAINTEXT_STORE, userId);
  await Promise.all([
    ...outbox.map((entry) => deleteOutboxEntry(entry.id)),
    ...cache.map((entry) => remove(CACHE_STORE, entry.id)),
    ...plaintext.map((entry) => remove(PLAINTEXT_STORE, entry.id))
  ]);
  for (const [id, entry] of memoryPlaintext) {
    if (entry.userId === userId) memoryPlaintext.delete(id);
  }
  for (const [id, entry] of memoryCache) {
    if (entry.userId === userId) memoryCache.delete(id);
  }
}
