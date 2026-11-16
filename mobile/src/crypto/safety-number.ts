/**
 * Safety numbers, using Signal's numeric fingerprint construction:
 * SHA-512 iterated 5200 times over (version || identity key || stable id),
 * first 30 bytes -> six 5-digit chunks per party. Both parties' halves are
 * sorted so each side sees the same 60 digits. Not interoperable with Signal
 * (different key encoding and identifiers), but the same security argument.
 */
import { sha512 } from '@noble/hashes/sha2.js';
import { concatBytes, utf8ToBytes } from '@noble/hashes/utils.js';
import { ED25519_KEY_BYTES, b64decode } from './wire';

const VERSION = new Uint8Array([0, 0]);
const ITERATIONS = 5200;

function chunk(hash: Uint8Array, offset: number): string {
  // 5 bytes as a big-endian 40-bit integer, then mod 100000.
  let value = 0;
  for (let i = 0; i < 5; i += 1) value = value * 256 + hash[offset + i];
  return String(value % 100000).padStart(5, '0');
}

/** 30-digit fingerprint for one party. */
export function displayableFingerprint(identityKey: string, userId: string): string {
  const key = b64decode(identityKey, ED25519_KEY_BYTES, 'identity key');
  let hash = concatBytes(VERSION, key, utf8ToBytes(userId));
  for (let i = 0; i < ITERATIONS; i += 1) hash = sha512(concatBytes(hash, key));
  return [0, 5, 10, 15, 20, 25].map((offset) => chunk(hash, offset)).join('');
}

/** 60-digit safety number shared by two parties (order-independent). */
export function safetyNumber(
  a: { identityKey: string; userId: string },
  b: { identityKey: string; userId: string }
): string {
  const parts = [
    displayableFingerprint(a.identityKey, a.userId),
    displayableFingerprint(b.identityKey, b.userId)
  ].sort();
  return parts.join('');
}

/** Split into 12 groups of 5 digits for display. */
export function groupDigits(digits: string): string[] {
  return digits.match(/.{1,5}/g) ?? [];
}
