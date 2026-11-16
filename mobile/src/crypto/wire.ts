/**
 * Canonical byte layouts for the E2EE key directory.
 *
 * Must stay byte-for-byte identical to backend/app/core/e2ee_wire.py; the shared
 * test vector in wire.test.ts / test_e2ee.py pins both sides.
 */
import { concatBytes, utf8ToBytes } from '@noble/hashes/utils.js';

export const ED25519_KEY_BYTES = 32;
export const ED25519_SIG_BYTES = 64;
export const X25519_KEY_BYTES = 32;
export const MLKEM768_PUBLIC_KEY_BYTES = 1184;

const label = (name: string) => utf8ToBytes(`relay-e2ee-v1/${name}\u0000`);
export const DEVICE_LABEL = label('device');
export const SIGNED_PREKEY_LABEL = label('spk');
export const PQ_PREKEY_LABEL = label('pqpk');

const NUL = new Uint8Array([0]);

export class WireError extends Error {}

export function b64encode(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** Strict unpadded base64url decode with an exact expected length. */
export function b64decode(value: string, expectedLength: number, what: string): Uint8Array {
  if (typeof value !== 'string' || !value || !/^[A-Za-z0-9_-]+$/.test(value)) {
    throw new WireError(`${what}: expected unpadded base64url`);
  }
  const padded = value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (value.length % 4)) % 4);
  let binary: string;
  try {
    binary = atob(padded);
  } catch {
    throw new WireError(`${what}: invalid base64url`);
  }
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  if (b64encode(bytes) !== value) throw new WireError(`${what}: non-canonical base64url`);
  if (bytes.length !== expectedLength) {
    throw new WireError(`${what}: expected ${expectedLength} bytes, got ${bytes.length}`);
  }
  return bytes;
}

/** Strict unpadded base64url decode for variable-length data (envelopes). */
export function b64decodeAny(value: string, maxLength: number, what: string): Uint8Array {
  if (typeof value !== 'string' || !value || value.length > Math.ceil((maxLength * 4) / 3)) {
    throw new WireError(`${what}: missing or too long`);
  }
  const padded = value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (value.length % 4)) % 4);
  if (!/^[A-Za-z0-9_-]+$/.test(value)) throw new WireError(`${what}: expected unpadded base64url`);
  let binary: string;
  try {
    binary = atob(padded);
  } catch {
    throw new WireError(`${what}: invalid base64url`);
  }
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  if (b64encode(bytes) !== value) throw new WireError(`${what}: non-canonical base64url`);
  return bytes;
}

function text(value: string): Uint8Array {
  if (value.includes('\u0000')) throw new WireError('identifiers must not contain NUL');
  return utf8ToBytes(value);
}

function u32be(value: number): Uint8Array {
  if (!Number.isInteger(value) || value < 0 || value > 0xffffffff) {
    throw new WireError('key_id out of range');
  }
  const out = new Uint8Array(4);
  new DataView(out.buffer).setUint32(0, value, false);
  return out;
}

/** What the account identity key signs to vouch for a device. */
export function deviceMessage(
  userId: string,
  deviceId: string,
  signingKey: Uint8Array,
  agreementKey: Uint8Array
): Uint8Array {
  return concatBytes(DEVICE_LABEL, text(userId), NUL, text(deviceId), NUL, signingKey, agreementKey);
}

/** What a device signing key signs for a signed or post-quantum prekey. */
export function prekeyMessage(
  prefix: Uint8Array,
  deviceId: string,
  keyId: number,
  publicKey: Uint8Array
): Uint8Array {
  return concatBytes(prefix, text(deviceId), NUL, u32be(keyId), publicKey);
}
