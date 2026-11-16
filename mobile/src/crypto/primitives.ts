/**
 * Thin wrappers over audited @noble primitives, with Relay's domain labels.
 * Everything that derives or uses a key goes through here so labels live in one place.
 */
import { gcm } from '@noble/ciphers/aes.js';
import { x25519 } from '@noble/curves/ed25519.js';
import { hkdf } from '@noble/hashes/hkdf.js';
import { hmac } from '@noble/hashes/hmac.js';
import { sha256 } from '@noble/hashes/sha2.js';
import { utf8ToBytes } from '@noble/hashes/utils.js';

export const INFO_PQXDH = utf8ToBytes('relay-e2ee-v1/pqxdh');
export const INFO_ROOT = utf8ToBytes('relay-e2ee-v1/rk');
export const INFO_MESSAGE = utf8ToBytes('relay-e2ee-v1/msg');

const ZERO_SALT = new Uint8Array(32);
const CHAIN_MESSAGE = new Uint8Array([0x01]);
const CHAIN_NEXT = new Uint8Array([0x02]);

export class CryptoError extends Error {}

/** X25519 with an explicit contributory check (no all-zero shared secrets). */
export function dh(privateKey: Uint8Array, publicKey: Uint8Array): Uint8Array {
  let shared: Uint8Array;
  try {
    shared = x25519.getSharedSecret(privateKey, publicKey);
  } catch {
    throw new CryptoError('invalid X25519 key');
  }
  if (shared.every((byte) => byte === 0)) throw new CryptoError('non-contributory X25519 output');
  return shared;
}

/** Root-chain KDF: (root key, DH output) -> (new root key, chain key). */
export function kdfRoot(rootKey: Uint8Array, dhOut: Uint8Array): [Uint8Array, Uint8Array] {
  const out = hkdf(sha256, dhOut, rootKey, INFO_ROOT, 64);
  return [out.slice(0, 32), out.slice(32)];
}

/** Symmetric-chain KDF: chain key -> (next chain key, message key). */
export function kdfChain(chainKey: Uint8Array): [Uint8Array, Uint8Array] {
  return [hmac(sha256, chainKey, CHAIN_NEXT), hmac(sha256, chainKey, CHAIN_MESSAGE)];
}

/** PQXDH secret derivation over the concatenated DH and KEM outputs. */
export function kdfPqxdh(ikm: Uint8Array): Uint8Array {
  return hkdf(sha256, ikm, ZERO_SALT, INFO_PQXDH, 32);
}

/**
 * AEAD for one message key. Each message key is used exactly once, so the
 * AES-GCM key and nonce are both derived from it (no nonce reuse possible).
 */
function messageCipher(messageKey: Uint8Array, associatedData: Uint8Array) {
  const okm = hkdf(sha256, messageKey, ZERO_SALT, INFO_MESSAGE, 44);
  return gcm(okm.slice(0, 32), okm.slice(32, 44), associatedData);
}

export function seal(messageKey: Uint8Array, plaintext: Uint8Array, associatedData: Uint8Array): Uint8Array {
  return messageCipher(messageKey, associatedData).encrypt(plaintext);
}

export function open(messageKey: Uint8Array, ciphertext: Uint8Array, associatedData: Uint8Array): Uint8Array {
  try {
    return messageCipher(messageKey, associatedData).decrypt(ciphertext);
  } catch {
    throw new CryptoError('message authentication failed');
  }
}
