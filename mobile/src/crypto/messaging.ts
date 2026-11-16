/**
 * Glue between the keystore, the directory and sessions, kept free of network
 * and storage so it can be tested directly. The e2ee store does the IO.
 */
import { utf8ToBytes } from '@noble/hashes/utils.js';
import { type DeviceWire, type SignedPrekeyWire, verifyDevice, verifyPqOneTimePrekey } from './keys';
import type { LocalDeviceState } from './keystore';
import { CryptoError } from './primitives';
import type { Consumed, LocalIdentity, PeerBundle, PrekeySecrets } from './session';

export const PAYLOAD_VERSION = 1;
const MAX_TEXT_LENGTH = 4000;

/** What travels inside an envelope. Never seen by the server. */
export interface MessagePayload {
  v: 1;
  text: string;
  reply_to_id?: string | null;
}

export interface ClaimedBundle {
  user_id: string;
  identity_key: string;
  device: DeviceWire;
  one_time_prekey: { key_id: number; public_key: string } | null;
  pq_one_time_prekey: SignedPrekeyWire | null;
}

export function encodePayload(payload: MessagePayload): Uint8Array {
  return utf8ToBytes(JSON.stringify(payload));
}

export function decodePayload(bytes: Uint8Array): MessagePayload {
  let value: unknown;
  try {
    value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
  } catch {
    throw new CryptoError('payload is not valid JSON');
  }
  const record = value as Partial<MessagePayload> | null;
  if (
    !record ||
    record.v !== PAYLOAD_VERSION ||
    typeof record.text !== 'string' ||
    record.text.length > MAX_TEXT_LENGTH ||
    (record.reply_to_id != null && typeof record.reply_to_id !== 'string')
  ) {
    throw new CryptoError('unsupported payload');
  }
  return { v: 1, text: record.text, reply_to_id: record.reply_to_id ?? null };
}

/**
 * Turn a server claim into a session bundle. The claim must be for the identity
 * key we already verified for this user, and every key in it must be signed.
 */
export function bundleFromClaim(claim: ClaimedBundle, userId: string, expectedIdentityKey: string): PeerBundle {
  if (claim.user_id !== userId || claim.identity_key !== expectedIdentityKey) {
    throw new CryptoError('claimed bundle does not match the verified identity');
  }
  verifyDevice(claim.identity_key, userId, claim.device);
  if (claim.pq_one_time_prekey) verifyPqOneTimePrekey(claim.device, claim.pq_one_time_prekey);
  const pq = claim.pq_one_time_prekey
    ? { key_id: claim.pq_one_time_prekey.key_id, public_key: claim.pq_one_time_prekey.public_key, oneTime: true }
    : { key_id: claim.device.pq_prekey.key_id, public_key: claim.device.pq_prekey.public_key, oneTime: false };
  return {
    identityKey: claim.identity_key,
    agreementKey: claim.device.agreement_key,
    signedPrekey: { key_id: claim.device.signed_prekey.key_id, public_key: claim.device.signed_prekey.public_key },
    pqPrekey: pq,
    oneTimePrekey: claim.one_time_prekey
  };
}

export function localIdentity(state: LocalDeviceState): LocalIdentity {
  if (!state.device) throw new CryptoError('device not provisioned');
  return { identityKey: state.identity.pub, agreement: state.device.agreement };
}

export function prekeySecrets(state: LocalDeviceState): PrekeySecrets {
  const device = state.device;
  if (!device) throw new CryptoError('device not provisioned');
  return {
    signedPrekey: (id) => {
      if (device.signedPrekey.id === id) return device.signedPrekey;
      if (device.previousSignedPrekey?.id === id) return device.previousSignedPrekey;
      return null;
    },
    pqPrekey: (id, oneTime) => {
      if (oneTime) return device.pqOneTime[id] ?? null;
      return device.pqPrekey.id === id ? device.pqPrekey.priv : null;
    },
    oneTimePrekey: (id) => device.oneTime[id] ?? null
  };
}

/** Forget one-time private keys a peer just used (forward secrecy for setup). */
export function consumePrekeys(state: LocalDeviceState, consumed: Consumed): boolean {
  const device = state.device;
  if (!device) return false;
  let changed = false;
  if (consumed.oneTimePrekeyId !== null && device.oneTime[consumed.oneTimePrekeyId]) {
    delete device.oneTime[consumed.oneTimePrekeyId];
    changed = true;
  }
  if (consumed.pqOneTimePrekeyId !== null && device.pqOneTime[consumed.pqOneTimePrekeyId]) {
    delete device.pqOneTime[consumed.pqOneTimePrekeyId];
    changed = true;
  }
  return changed;
}
