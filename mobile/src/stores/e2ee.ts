import { defineStore } from 'pinia';
import { ApiError, apiFetch } from '@/api/client';
import {
  type DeviceWire,
  type OneTimePrekeyWire,
  type StoredPrekey,
  generateAgreementKey,
  generateIdentity,
  generatePqKey,
  generateSigningKey,
  newDeviceId,
  pqPrekeyWire,
  signDevice,
  signedPrekeyWire,
  verifyDevice
} from '@/crypto/keys';
import {
  type LocalDeviceState,
  type PinnedIdentity,
  loadState,
  loadTrust,
  saveState,
  saveTrust
} from '@/crypto/keystore';
import { safetyNumber } from '@/crypto/safety-number';
import { reportError } from '@/services/errors';
import { useAuthStore } from '@/stores/auth';

export const EC_POOL_SIZE = 50;
export const KEM_POOL_SIZE = 10;
export const SIGNED_PREKEY_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

export type E2eeStatus = 'idle' | 'working' | 'ready' | 'needs-link' | 'error';

interface UserKeys {
  user_id: string;
  identity_key: string;
  devices: DeviceWire[];
}

interface OwnDevice extends DeviceWire {
  prekeys: { one_time_prekeys: number; pq_one_time_prekeys: number };
}

export interface ContactKeys {
  userId: string;
  identityKey: string;
  devices: DeviceWire[];
  /** Devices the server returned that failed signature checks (never used). */
  rejectedDevices: number;
  pinned: PinnedIdentity;
}

let ensurePromise: Promise<void> | null = null;

function prekey(id: number, pair: { pub: string; priv: string }): StoredPrekey {
  return { id, pub: pair.pub, priv: pair.priv, createdAt: Date.now() };
}

async function fetchUserKeys(userId: string): Promise<UserKeys | null> {
  try {
    return await apiFetch<UserKeys>(`/e2ee/users/${encodeURIComponent(userId)}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/** Generate one-time prekeys, recording private halves in `device` before upload. */
function generateOneTime(
  device: NonNullable<LocalDeviceState['device']>,
  ecCount: number,
  kemCount: number
): { ec: OneTimePrekeyWire[]; kem: ReturnType<typeof pqPrekeyWire>[] } {
  const ec: OneTimePrekeyWire[] = [];
  const kem: ReturnType<typeof pqPrekeyWire>[] = [];
  for (let i = 0; i < ecCount; i += 1) {
    const id = device.nextKeyId++;
    const pair = generateAgreementKey();
    device.oneTime[id] = pair.priv;
    ec.push({ key_id: id, public_key: pair.pub });
  }
  for (let i = 0; i < kemCount; i += 1) {
    const id = device.nextKeyId++;
    const pair = generatePqKey();
    device.pqOneTime[id] = pair.priv;
    kem.push(pqPrekeyWire(device.signing, device.deviceId, prekey(id, pair)));
  }
  return { ec, kem };
}

function newDevice(): NonNullable<LocalDeviceState['device']> {
  const device = {
    deviceId: newDeviceId(),
    signing: generateSigningKey(),
    agreement: generateAgreementKey(),
    signedPrekey: prekey(1, generateAgreementKey()),
    pqPrekey: prekey(2, generatePqKey()),
    oneTime: {},
    pqOneTime: {},
    nextKeyId: 3,
    registered: false
  };
  return device;
}

export const useE2eeStore = defineStore('e2ee', {
  state: () => ({
    status: 'idle' as E2eeStatus,
    deviceId: null as string | null,
    identityKey: null as string | null,
    userId: null as string | null
  }),
  actions: {
    reset() {
      this.status = 'idle';
      this.deviceId = null;
      this.identityKey = null;
      this.userId = null;
      ensurePromise = null;
    },

    /** Make sure this device has an identity, a registered device and enough prekeys. */
    ensure(): Promise<void> {
      if (!ensurePromise) {
        ensurePromise = this.runEnsure().finally(() => {
          ensurePromise = null;
        });
      }
      return ensurePromise;
    },

    async runEnsure() {
      const auth = useAuthStore();
      const userId = auth.user?.id;
      if (!userId) return;
      this.status = 'working';
      this.userId = userId;
      try {
        let state = await loadState(userId);
        const server = await fetchUserKeys(userId);

        if (!server) {
          // The server knows no identity, so any device we think is registered is
          // stale (e.g. server data reset): keep the identity, re-create the device.
          const identity = state?.identity ?? generateIdentity();
          const device = state?.device && !state.device.registered ? state.device : null;
          state = { userId, identity, device };
          await saveState(state);
          await apiFetch('/e2ee/identity', {
            method: 'PUT',
            body: JSON.stringify({ identity_key: identity.pub })
          });
        } else if (!state || state.identity.pub !== server.identity_key) {
          // Another device holds this account's identity. Device linking (Phase 2)
          // or an explicit identity reset is required; never silently replace it.
          this.identityKey = server.identity_key;
          this.status = 'needs-link';
          return;
        }

        const revoked = state.device?.registered && server
          ? !server.devices.some((device) => device.device_id === state!.device!.deviceId)
          : false;
        if (!state.device || revoked) {
          state.device = newDevice();
        }
        if (!state.device.registered) await this.registerDevice(state);
        await this.topUp(state);

        this.identityKey = state.identity.pub;
        this.deviceId = state.device.deviceId;
        this.status = 'ready';
      } catch (error) {
        this.status = 'error';
        reportError('e2ee.ensure', error);
      }
    },

    async registerDevice(state: LocalDeviceState) {
      const device = state.device!;
      const { ec, kem } = generateOneTime(device, EC_POOL_SIZE, KEM_POOL_SIZE);
      // Persist private halves first: published keys we cannot decrypt with would
      // make every session started against them undecryptable.
      await saveState(state);
      await apiFetch('/e2ee/devices', {
        method: 'POST',
        body: JSON.stringify({
          device_id: device.deviceId,
          label: null,
          signing_key: device.signing.pub,
          agreement_key: device.agreement.pub,
          identity_signature: signDevice(
            state.identity,
            state.userId,
            device.deviceId,
            device.signing,
            device.agreement
          ),
          signed_prekey: signedPrekeyWire(device.signing, device.deviceId, device.signedPrekey),
          pq_prekey: pqPrekeyWire(device.signing, device.deviceId, device.pqPrekey),
          one_time_prekeys: ec,
          pq_one_time_prekeys: kem
        })
      });
      device.registered = true;
      await saveState(state);
    },

    /** Refill one-time prekeys below half the pool and rotate an old signed prekey. */
    async topUp(state: LocalDeviceState) {
      const device = state.device!;
      const own = await apiFetch<OwnDevice[]>('/e2ee/devices');
      const mine = own.find((entry) => entry.device_id === device.deviceId);
      if (!mine) return;
      const ecMissing = mine.prekeys.one_time_prekeys < EC_POOL_SIZE / 2
        ? EC_POOL_SIZE - mine.prekeys.one_time_prekeys
        : 0;
      const kemMissing = mine.prekeys.pq_one_time_prekeys < KEM_POOL_SIZE / 2
        ? KEM_POOL_SIZE - mine.prekeys.pq_one_time_prekeys
        : 0;
      const rotate = Date.now() - device.signedPrekey.createdAt > SIGNED_PREKEY_MAX_AGE_MS;
      if (!ecMissing && !kemMissing && !rotate) return;

      const { ec, kem } = generateOneTime(device, ecMissing, kemMissing);
      let signed: ReturnType<typeof signedPrekeyWire> | undefined;
      if (rotate) {
        device.previousSignedPrekey = device.signedPrekey;
        device.signedPrekey = prekey(device.nextKeyId++, generateAgreementKey());
        signed = signedPrekeyWire(device.signing, device.deviceId, device.signedPrekey);
      }
      await saveState(state);
      await apiFetch(`/e2ee/devices/${encodeURIComponent(device.deviceId)}/prekeys`, {
        method: 'PUT',
        body: JSON.stringify({
          signed_prekey: signed,
          one_time_prekeys: ec,
          pq_one_time_prekeys: kem
        })
      });
    },

    /** Replace a lost identity. Revokes every device; contacts see a key change. */
    async resetIdentity(password: string) {
      const auth = useAuthStore();
      const userId = auth.user?.id;
      if (!userId) throw new Error('Authentication is required');
      const identity = generateIdentity();
      const state: LocalDeviceState = { userId, identity, device: null };
      await saveState(state);
      await apiFetch('/e2ee/identity', {
        method: 'PUT',
        body: JSON.stringify({ identity_key: identity.pub, replace: true, password })
      });
      await this.ensure();
    },

    /**
     * Fetch a contact's keys, keep only devices whose signatures verify, and
     * compare the identity against the locally pinned one (trust on first use).
     */
    async contactKeys(contactId: string): Promise<ContactKeys | null> {
      const me = this.userId ?? useAuthStore().user?.id;
      if (!me) return null;
      const keys = await fetchUserKeys(contactId);
      if (!keys) return null;

      const devices: DeviceWire[] = [];
      let rejectedDevices = 0;
      for (const device of keys.devices) {
        try {
          verifyDevice(keys.identity_key, contactId, device);
          devices.push(device);
        } catch (error) {
          rejectedDevices += 1;
          reportError('e2ee.verifyDevice', error);
        }
      }

      const trust = await loadTrust(me);
      let pinned = trust[contactId];
      if (!pinned) {
        pinned = { identityKey: keys.identity_key, firstSeenAt: Date.now(), verified: false };
        trust[contactId] = pinned;
        await saveTrust(me, trust);
      } else if (pinned.identityKey !== keys.identity_key && pinned.changedTo !== keys.identity_key) {
        pinned = { ...pinned, verified: false, changedTo: keys.identity_key };
        trust[contactId] = pinned;
        await saveTrust(me, trust);
      }
      return { userId: contactId, identityKey: keys.identity_key, devices, rejectedDevices, pinned };
    },

    async setVerified(contactId: string, verified: boolean) {
      const me = this.userId;
      if (!me) return;
      const trust = await loadTrust(me);
      const pinned = trust[contactId];
      if (!pinned || pinned.changedTo) return;
      trust[contactId] = { ...pinned, verified };
      await saveTrust(me, trust);
    },

    /** Accept a contact's new identity key after a change warning. */
    async acceptKeyChange(contactId: string) {
      const me = this.userId;
      if (!me) return;
      const trust = await loadTrust(me);
      const pinned = trust[contactId];
      if (!pinned?.changedTo) return;
      trust[contactId] = {
        identityKey: pinned.changedTo,
        firstSeenAt: Date.now(),
        verified: false,
        changedTo: null
      };
      await saveTrust(me, trust);
    },

    safetyNumberWith(contact: ContactKeys): string | null {
      if (!this.identityKey || !this.userId) return null;
      return safetyNumber(
        { identityKey: this.identityKey, userId: this.userId },
        { identityKey: contact.identityKey, userId: contact.userId }
      );
    }
  }
});
