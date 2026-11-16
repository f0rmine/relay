import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  type DeviceWire,
  generateAgreementKey,
  generateIdentity,
  generatePqKey,
  generateSigningKey,
  pqPrekeyWire,
  signDevice,
  signedPrekeyWire,
  verifyDevice
} from '@/crypto/keys';
import type { LocalDeviceState, TrustStore } from '@/crypto/keystore';

const mocks = vi.hoisted(() => ({
  apiFetch: vi.fn(),
  reportError: vi.fn(),
  storage: new Map<string, string>(),
  events: [] as string[]
}));

vi.mock('@/api/client', () => {
  class ApiError extends Error {
    constructor(public status: number, message: string) {
      super(message);
    }
  }
  return { ApiError, apiFetch: mocks.apiFetch, setRelayDeviceId: vi.fn() };
});
vi.mock('@/services/errors', () => ({ reportError: mocks.reportError }));
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { id: 'me' } }) }));
vi.mock('@/crypto/keystore', () => ({
  loadState: async (userId: string) => {
    const raw = mocks.storage.get(`state:${userId}`);
    return raw ? (JSON.parse(raw) as LocalDeviceState) : null;
  },
  saveState: async (state: LocalDeviceState) => {
    mocks.events.push('saveState');
    mocks.storage.set(`state:${state.userId}`, JSON.stringify(state));
  },
  loadTrust: async (userId: string) => JSON.parse(mocks.storage.get(`trust:${userId}`) ?? '{}') as TrustStore,
  saveTrust: async (userId: string, trust: TrustStore) => {
    mocks.storage.set(`trust:${userId}`, JSON.stringify(trust));
  }
}));

import { ApiError } from '@/api/client';
import { EC_POOL_SIZE, KEM_POOL_SIZE, useE2eeStore } from './e2ee';

const notFound = () => new (ApiError as unknown as new (s: number, m: string) => Error)(404, 'nope');

function savedState(): LocalDeviceState {
  return JSON.parse(mocks.storage.get('state:me')!) as LocalDeviceState;
}

function contactDevice(userId: string, identity = generateIdentity()): { identity: typeof identity; device: DeviceWire } {
  const signing = generateSigningKey();
  const agreement = generateAgreementKey();
  const deviceId = 'contact-device-1';
  return {
    identity,
    device: {
      device_id: deviceId,
      signing_key: signing.pub,
      agreement_key: agreement.pub,
      identity_signature: signDevice(identity, userId, deviceId, signing, agreement),
      signed_prekey: signedPrekeyWire(signing, deviceId, { id: 1, createdAt: 0, ...generateAgreementKey() }),
      pq_prekey: pqPrekeyWire(signing, deviceId, { id: 2, createdAt: 0, ...generatePqKey() })
    }
  };
}

describe('e2ee store', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    mocks.apiFetch.mockReset();
    mocks.reportError.mockReset();
    mocks.storage.clear();
    mocks.events.length = 0;
  });

  it('provisions a fresh account and keeps every uploaded private key', async () => {
    let posted: Record<string, unknown> | null = null;
    let identityKey = '';
    mocks.apiFetch.mockImplementation(async (path: string, init?: RequestInit) => {
      mocks.events.push(`${init?.method ?? 'GET'} ${path}`);
      if (path === '/e2ee/users/me') throw notFound();
      if (path === '/e2ee/identity') {
        identityKey = JSON.parse(String(init!.body)).identity_key;
        return { identity_key: identityKey };
      }
      if (path === '/e2ee/devices' && init?.method === 'POST') {
        posted = JSON.parse(String(init.body));
        return {};
      }
      if (path === '/e2ee/devices') {
        return [{ device_id: posted!.device_id, prekeys: { one_time_prekeys: EC_POOL_SIZE, pq_one_time_prekeys: KEM_POOL_SIZE } }];
      }
      throw new Error(`unexpected ${path}`);
    });

    const store = useE2eeStore();
    await store.ensure();

    expect(store.status).toBe('ready');
    expect(mocks.reportError).not.toHaveBeenCalled();
    const body = posted as unknown as DeviceWire & { one_time_prekeys: unknown[]; pq_one_time_prekeys: unknown[] };
    // The device we publish verifies against the identity we registered.
    expect(() => verifyDevice(identityKey, 'me', body)).not.toThrow();
    expect(body.one_time_prekeys).toHaveLength(EC_POOL_SIZE);
    expect(body.pq_one_time_prekeys).toHaveLength(KEM_POOL_SIZE);

    const state = savedState();
    expect(state.identity.pub).toBe(identityKey);
    expect(Object.keys(state.device!.oneTime)).toHaveLength(EC_POOL_SIZE);
    expect(Object.keys(state.device!.pqOneTime)).toHaveLength(KEM_POOL_SIZE);
    expect(state.device!.registered).toBe(true);
    // Private halves hit storage before the public halves left the device.
    expect(mocks.events.indexOf('saveState')).toBeLessThan(mocks.events.indexOf('POST /e2ee/devices'));
  });

  it('never replaces an identity held by another device', async () => {
    mocks.apiFetch.mockImplementation(async (path: string) => {
      if (path === '/e2ee/users/me') return { user_id: 'me', identity_key: generateIdentity().pub, devices: [] };
      throw new Error(`unexpected ${path}`);
    });
    const store = useE2eeStore();
    await store.ensure();
    expect(store.status).toBe('needs-link');
    expect(mocks.apiFetch).toHaveBeenCalledTimes(1);
  });

  it('tops up one-time prekeys when the server pool runs low', async () => {
    // First provision normally.
    let deviceId = '';
    let counts = { one_time_prekeys: EC_POOL_SIZE, pq_one_time_prekeys: KEM_POOL_SIZE };
    let identityKey = '';
    let uploaded: { one_time_prekeys: unknown[]; pq_one_time_prekeys: unknown[] } | null = null;
    mocks.apiFetch.mockImplementation(async (path: string, init?: RequestInit) => {
      if (path === '/e2ee/users/me') {
        if (!identityKey) throw notFound();
        return { user_id: 'me', identity_key: identityKey, devices: [{ device_id: deviceId }] };
      }
      if (path === '/e2ee/identity') {
        identityKey = JSON.parse(String(init!.body)).identity_key;
        return {};
      }
      if (path === '/e2ee/devices' && init?.method === 'POST') {
        deviceId = JSON.parse(String(init.body)).device_id;
        return {};
      }
      if (path === '/e2ee/devices') return [{ device_id: deviceId, prekeys: counts }];
      if (path.endsWith('/prekeys')) {
        uploaded = JSON.parse(String(init!.body));
        return {};
      }
      throw new Error(`unexpected ${path}`);
    });
    const store = useE2eeStore();
    await store.ensure();
    expect(uploaded).toBeNull();

    counts = { one_time_prekeys: 10, pq_one_time_prekeys: 1 };
    await store.ensure();
    expect(store.status).toBe('ready');
    expect(uploaded!.one_time_prekeys).toHaveLength(EC_POOL_SIZE - 10);
    expect(uploaded!.pq_one_time_prekeys).toHaveLength(KEM_POOL_SIZE - 1);
    expect(Object.keys(savedState().device!.oneTime)).toHaveLength(EC_POOL_SIZE * 2 - 10);
  });

  it('pins contacts on first use, flags key changes and drops forged devices', async () => {
    const store = useE2eeStore();
    store.userId = 'me';
    store.identityKey = generateIdentity().pub;

    const first = contactDevice('bob');
    const forged = contactDevice('bob'); // signed by a different identity
    let served = { user_id: 'bob', identity_key: first.identity.pub, devices: [first.device, forged.device] };
    mocks.apiFetch.mockImplementation(async () => served);

    const pinned = await store.contactKeys('bob');
    expect(pinned!.devices).toHaveLength(1);
    expect(pinned!.rejectedDevices).toBe(1);
    expect(pinned!.pinned.identityKey).toBe(first.identity.pub);
    expect(store.safetyNumberWith(pinned!)).toMatch(/^\d{60}$/);

    await store.setVerified('bob', true);
    expect((await store.contactKeys('bob'))!.pinned.verified).toBe(true);

    const rekeyed = contactDevice('bob');
    served = { user_id: 'bob', identity_key: rekeyed.identity.pub, devices: [rekeyed.device] };
    const changed = await store.contactKeys('bob');
    expect(changed!.pinned.changedTo).toBe(rekeyed.identity.pub);
    expect(changed!.pinned.verified).toBe(false);
    expect(changed!.pinned.identityKey).toBe(first.identity.pub);

    await store.acceptKeyChange('bob');
    const accepted = await store.contactKeys('bob');
    expect(accepted!.pinned.identityKey).toBe(rekeyed.identity.pub);
    expect(accepted!.pinned.changedTo).toBeNull();
  });
});
