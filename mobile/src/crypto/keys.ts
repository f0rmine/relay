/**
 * Key generation and verification for the E2EE key directory (Phase 1).
 * Primitives: @noble/curves (audited) and ML-KEM-768 from @noble/post-quantum.
 */
import { ed25519, x25519 } from '@noble/curves/ed25519.js';
import { ml_kem768 } from '@noble/post-quantum/ml-kem.js';
import { randomBytes } from '@noble/hashes/utils.js';
import {
  ED25519_KEY_BYTES,
  ED25519_SIG_BYTES,
  MLKEM768_PUBLIC_KEY_BYTES,
  PQ_PREKEY_LABEL,
  SIGNED_PREKEY_LABEL,
  X25519_KEY_BYTES,
  WireError,
  b64decode,
  b64encode,
  deviceMessage,
  prekeyMessage
} from './wire';

/** A key pair with base64url-encoded halves, safe to JSON-serialise into the keystore. */
export interface StoredKeyPair {
  pub: string;
  priv: string;
}

export interface StoredPrekey extends StoredKeyPair {
  id: number;
  createdAt: number;
}

export interface SignedPrekeyWire {
  key_id: number;
  public_key: string;
  signature: string;
}

export interface OneTimePrekeyWire {
  key_id: number;
  public_key: string;
}

export interface DeviceWire {
  device_id: string;
  signing_key: string;
  agreement_key: string;
  identity_signature: string;
  signed_prekey: SignedPrekeyWire;
  pq_prekey: SignedPrekeyWire;
  created_at?: string;
  label?: string | null;
}

const pair = (pub: Uint8Array, priv: Uint8Array): StoredKeyPair => ({
  pub: b64encode(pub),
  priv: b64encode(priv)
});

export function generateIdentity(): StoredKeyPair {
  const { secretKey, publicKey } = ed25519.keygen();
  return pair(publicKey, secretKey);
}

export function generateSigningKey(): StoredKeyPair {
  const { secretKey, publicKey } = ed25519.keygen();
  return pair(publicKey, secretKey);
}

export function generateAgreementKey(): StoredKeyPair {
  const { secretKey, publicKey } = x25519.keygen();
  return pair(publicKey, secretKey);
}

export function generatePqKey(): StoredKeyPair {
  const { secretKey, publicKey } = ml_kem768.keygen();
  return pair(publicKey, secretKey);
}

/** Random URL-safe device id; never reused after revocation. */
export function newDeviceId(): string {
  return b64encode(randomBytes(18));
}

function secret(key: StoredKeyPair): Uint8Array {
  return b64decode(key.priv, ED25519_KEY_BYTES, 'private key');
}

export function signDevice(
  identity: StoredKeyPair,
  userId: string,
  deviceId: string,
  signing: StoredKeyPair,
  agreement: StoredKeyPair
): string {
  const message = deviceMessage(
    userId,
    deviceId,
    b64decode(signing.pub, ED25519_KEY_BYTES, 'signing key'),
    b64decode(agreement.pub, X25519_KEY_BYTES, 'agreement key')
  );
  return b64encode(ed25519.sign(message, secret(identity)));
}

export function signedPrekeyWire(
  signing: StoredKeyPair,
  deviceId: string,
  prekey: StoredPrekey
): SignedPrekeyWire {
  const pub = b64decode(prekey.pub, X25519_KEY_BYTES, 'signed prekey');
  const message = prekeyMessage(SIGNED_PREKEY_LABEL, deviceId, prekey.id, pub);
  return { key_id: prekey.id, public_key: prekey.pub, signature: b64encode(ed25519.sign(message, secret(signing))) };
}

export function pqPrekeyWire(
  signing: StoredKeyPair,
  deviceId: string,
  prekey: StoredPrekey
): SignedPrekeyWire {
  const pub = b64decode(prekey.pub, MLKEM768_PUBLIC_KEY_BYTES, 'pq prekey');
  const message = prekeyMessage(PQ_PREKEY_LABEL, deviceId, prekey.id, pub);
  return { key_id: prekey.id, public_key: prekey.pub, signature: b64encode(ed25519.sign(message, secret(signing))) };
}

function verifySignature(pub: Uint8Array, signature: string, message: Uint8Array, what: string): void {
  const sig = b64decode(signature, ED25519_SIG_BYTES, `${what} signature`);
  if (!ed25519.verify(sig, message, pub)) throw new WireError(`${what}: signature verification failed`);
}

/**
 * Verify a device record fetched from the (untrusted) server: it must be vouched
 * for by the account identity key and its prekeys signed by the device key.
 * Throws WireError if anything does not check out.
 */
export function verifyDevice(identityKey: string, userId: string, device: DeviceWire): void {
  const identity = b64decode(identityKey, ED25519_KEY_BYTES, 'identity key');
  const signing = b64decode(device.signing_key, ED25519_KEY_BYTES, 'signing key');
  const agreement = b64decode(device.agreement_key, X25519_KEY_BYTES, 'agreement key');
  verifySignature(
    identity,
    device.identity_signature,
    deviceMessage(userId, device.device_id, signing, agreement),
    'device'
  );
  const spk = b64decode(device.signed_prekey.public_key, X25519_KEY_BYTES, 'signed prekey');
  verifySignature(
    signing,
    device.signed_prekey.signature,
    prekeyMessage(SIGNED_PREKEY_LABEL, device.device_id, device.signed_prekey.key_id, spk),
    'signed prekey'
  );
  const pq = b64decode(device.pq_prekey.public_key, MLKEM768_PUBLIC_KEY_BYTES, 'pq prekey');
  verifySignature(
    signing,
    device.pq_prekey.signature,
    prekeyMessage(PQ_PREKEY_LABEL, device.device_id, device.pq_prekey.key_id, pq),
    'pq prekey'
  );
}
