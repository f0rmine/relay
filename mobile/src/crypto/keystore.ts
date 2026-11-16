/**
 * Persistence for E2EE private key material and pinned contact keys.
 *
 * Native builds use the platform keystore (Android Keystore / iOS Keychain via
 * capacitor-secure-storage). The browser build used for development falls back
 * to localStorage, which offers no protection at rest; E2EE must not be
 * advertised for the web build.
 */
import { Capacitor } from '@capacitor/core';
import { SecureStorage } from '@aparajita/capacitor-secure-storage';
import type { StoredKeyPair, StoredPrekey } from './keys';

const useSecureStorage = Capacitor.isNativePlatform();
const PREFIX = 'e2ee:v1:';

export interface LocalDeviceState {
  userId: string;
  identity: StoredKeyPair;
  device: {
    deviceId: string;
    signing: StoredKeyPair;
    agreement: StoredKeyPair;
    signedPrekey: StoredPrekey;
    pqPrekey: StoredPrekey;
    /** Private halves of one-time prekeys still on the server, by key id. */
    oneTime: Record<string, string>;
    pqOneTime: Record<string, string>;
    nextKeyId: number;
    registered: boolean;
  } | null;
}

export interface PinnedIdentity {
  identityKey: string;
  firstSeenAt: number;
  verified: boolean;
  /** Set when the server starts returning a different key; cleared on acknowledgement. */
  changedTo?: string | null;
}

export type TrustStore = Record<string, PinnedIdentity>;

async function read(key: string): Promise<string | null> {
  if (useSecureStorage) {
    const value = await SecureStorage.getItem(key);
    return typeof value === 'string' ? value : null;
  }
  return localStorage.getItem(key);
}

async function write(key: string, value: string): Promise<void> {
  if (useSecureStorage) {
    await SecureStorage.setItem(key, value);
    return;
  }
  localStorage.setItem(key, value);
}

async function remove(key: string): Promise<void> {
  if (useSecureStorage) {
    await SecureStorage.removeItem(key);
    return;
  }
  localStorage.removeItem(key);
}

function parse<T>(raw: string | null): T | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

const stateKey = (userId: string) => `${PREFIX}state:${userId}`;
const trustKey = (userId: string) => `${PREFIX}trust:${userId}`;

export async function loadState(userId: string): Promise<LocalDeviceState | null> {
  const state = parse<LocalDeviceState>(await read(stateKey(userId)));
  return state && state.userId === userId ? state : null;
}

export async function saveState(state: LocalDeviceState): Promise<void> {
  await write(stateKey(state.userId), JSON.stringify(state));
}

export async function clearState(userId: string): Promise<void> {
  await remove(stateKey(userId));
  await remove(trustKey(userId));
}

/** Contacts' pinned identity keys, scoped to the local account. */
export async function loadTrust(userId: string): Promise<TrustStore> {
  return parse<TrustStore>(await read(trustKey(userId))) ?? {};
}

export async function saveTrust(userId: string, trust: TrustStore): Promise<void> {
  await write(trustKey(userId), JSON.stringify(trust));
}
