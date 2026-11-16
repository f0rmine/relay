import { defineStore } from 'pinia';
import { ApiError, apiFetch, setRelayDeviceId } from '@/api/client';
import type { Conversation, Message } from '@/api/types';
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
  loadSession,
  loadState,
  loadTrust,
  saveSession,
  saveState,
  saveTrust
} from '@/crypto/keystore';
import {
  type ClaimedBundle,
  type MessagePayload,
  bundleFromClaim,
  consumePrekeys,
  decodePayload,
  encodePayload,
  localIdentity,
  prekeySecrets
} from '@/crypto/messaging';
import { decrypt as decryptEnvelope, encrypt as encryptEnvelope, startSession } from '@/crypto/session';
import { b64decodeAny, b64encode } from '@/crypto/wire';
import { loadPlaintext, savePlaintext } from '@/services/message-storage';
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

/** Max decoded envelope size accepted from the server (padded 4000 chars + prekey header). */
const MAX_ENVELOPE_BYTES = 12_288;
const KEYS_TTL_MS = 30_000;

export type E2eeErrorCode = 'not-ready' | 'peer-not-ready' | 'safety-number-changed' | 'needs-link';

export class E2eeError extends Error {
  constructor(public code: E2eeErrorCode) {
    super(code);
  }
}

export interface OutgoingEnvelope {
  user_id: string;
  device_id: string;
  ciphertext: string;
}

// One lock for every session / prekey mutation: decrypting and encrypting both
// advance ratchets and may consume one-time keys, and must never interleave.
let lockTail: Promise<unknown> = Promise.resolve();
function withLock<T>(task: () => Promise<T>): Promise<T> {
  const run = lockTail.then(task, task);
  lockTail = run.catch(() => undefined);
  return run;
}

const keysCache = new Map<string, { at: number; keys: ContactKeys | null }>();

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
      keysCache.clear();
      setRelayDeviceId(null);
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
        setRelayDeviceId(state.device.deviceId);
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

    invalidateKeys() {
      keysCache.clear();
    },

    /** Verified keys for a user, cached briefly. Own account: devices checked against our identity. */
    async verifiedKeys(userId: string, fresh = false): Promise<ContactKeys | null> {
      const cached = keysCache.get(userId);
      if (!fresh && cached && Date.now() - cached.at < KEYS_TTL_MS) return cached.keys;
      let keys: ContactKeys | null;
      if (userId === this.userId) {
        const own = await fetchUserKeys(userId);
        if (!own || own.identity_key !== this.identityKey) throw new E2eeError('needs-link');
        const devices = own.devices.filter((device) => {
          try {
            verifyDevice(own.identity_key, userId, device);
            return true;
          } catch (error) {
            reportError('e2ee.verifyOwnDevice', error);
            return false;
          }
        });
        keys = {
          userId,
          identityKey: own.identity_key,
          devices,
          rejectedDevices: own.devices.length - devices.length,
          pinned: { identityKey: own.identity_key, firstSeenAt: 0, verified: true }
        };
      } else {
        keys = await this.contactKeys(userId);
      }
      keysCache.set(userId, { at: Date.now(), keys });
      return keys;
    },

    /** Encrypt one payload for every device in the conversation except this one. */
    encryptForConversation(
      conversation: Conversation,
      payload: MessagePayload,
      freshKeys = false
    ): Promise<{ envelopes: OutgoingEnvelope[]; sender_device_id: string }> {
      return withLock(async () => {
        await this.ensure();
        const me = this.userId;
        const state = me ? await loadState(me) : null;
        if (this.status !== 'ready' || !me || !state?.device?.registered) throw new E2eeError('not-ready');
        const plaintext = encodePayload(payload);
        const envelopes: OutgoingEnvelope[] = [];
        for (const participant of conversation.participants) {
          const keys = await this.verifiedKeys(participant.id, freshKeys);
          if (!keys || !keys.devices.length) throw new E2eeError('peer-not-ready');
          // A changed, unacknowledged safety number blocks sending until reviewed.
          if (keys.pinned.changedTo) throw new E2eeError('safety-number-changed');
          for (const device of keys.devices) {
            if (participant.id === me && device.device_id === state.device.deviceId) continue;
            let session = await loadSession(me, participant.id, device.device_id);
            if (!session) {
              const claim = await apiFetch<ClaimedBundle>(
                `/e2ee/users/${encodeURIComponent(participant.id)}/devices/${encodeURIComponent(device.device_id)}/claim`,
                { method: 'POST' }
              );
              session = startSession(localIdentity(state), bundleFromClaim(claim, participant.id, keys.identityKey));
            }
            const { session: next, envelope } = encryptEnvelope(session, plaintext);
            await saveSession(me, participant.id, device.device_id, next);
            envelopes.push({ user_id: participant.id, device_id: device.device_id, ciphertext: b64encode(envelope) });
          }
        }
        return { envelopes, sender_device_id: state.device.deviceId };
      });
    },

    /**
     * Resolve an E2EE message's text: from the local plaintext store if we have
     * seen it, otherwise by decrypting this device's envelope exactly once.
     */
    async decryptMessage(message: Message): Promise<Message> {
      if (!message.e2ee || message.deleted_at) return message;
      const me = this.userId ?? useAuthStore().user?.id;
      if (!me) return message;
      const known = await loadPlaintext(me, message.id);
      if (known) return { ...message, text: known.text, undecryptable: false };
      let envelope = message.envelope ?? (this.deviceId ? message.envelopes?.[this.deviceId] : null);
      const fromThisDevice = message.sender_id === me && message.sender_device_id === this.deviceId;
      if (!envelope && !fromThisDevice && this.deviceId) {
        // Some events (e.g. scheduled-message dispatch) arrive without envelopes.
        try {
          envelope = (await apiFetch<{ envelope: string }>(`/messages/${encodeURIComponent(message.id)}/envelope`)).envelope;
        } catch (error) {
          if (!(error instanceof ApiError && error.status === 404)) reportError('e2ee.fetchEnvelope', error);
        }
      }
      if (!envelope || !message.sender_device_id) return { ...message, text: null, undecryptable: true };

      try {
        return await withLock(async () => {
          // Another path may have decrypted it while we waited for the lock.
          const again = await loadPlaintext(me, message.id);
          if (again) return { ...message, text: again.text, undecryptable: false };
          const state = await loadState(me);
          if (!state?.device) throw new E2eeError('not-ready');
          const keys = await this.verifiedKeys(message.sender_id);
          const device = keys?.devices.find((entry) => entry.device_id === message.sender_device_id);
          if (!keys || !device) throw new E2eeError('peer-not-ready');

          const existing = await loadSession(me, message.sender_id, device.device_id);
          const result = decryptEnvelope(
            localIdentity(state),
            prekeySecrets(state),
            existing,
            b64decodeAny(envelope, MAX_ENVELOPE_BYTES, 'envelope'),
            { identityKey: keys.identityKey, agreementKey: device.agreement_key }
          );
          const payload = decodePayload(result.plaintext);
          // Persist the plaintext before advancing the session: if we crash in
          // between, the unchanged session can still decrypt the redelivery.
          await savePlaintext(me, message.conversation_id, message.id, {
            text: payload.text,
            reply_to_id: payload.reply_to_id ?? null
          });
          await saveSession(me, message.sender_id, device.device_id, result.session);
          if (consumePrekeys(state, result.consumed)) await saveState(state);
          return { ...message, text: payload.text, undecryptable: false };
        });
      } catch (error) {
        reportError('e2ee.decrypt', error);
        return { ...message, text: null, undecryptable: true };
      }
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
