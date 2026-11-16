/**
 * Device-to-device sessions: PQXDH setup (Signal PQXDH spec, rev. 3) feeding a
 * Double Ratchet, plus the envelope wire format.
 *
 * Envelope formats (all integers big-endian):
 *   0x01 message:  [0x01][ratchet header 40][AES-GCM ciphertext]
 *   0x02 prekey:   [0x02][sender AIK 32][sender agreement key 32][ephemeral 32]
 *                  [signed prekey id 4][pq prekey id 4][pq one-time 1]
 *                  [has one-time prekey 1][one-time prekey id 4][ML-KEM ct 1088]
 *                  [inner 0x01 message ...]
 *
 * The initiator keeps sending the prekey form until it receives any reply, so
 * the responder can set up the session from whichever message arrives first.
 */
import { x25519 } from '@noble/curves/ed25519.js';
import { ml_kem768 } from '@noble/post-quantum/ml-kem.js';
import { concatBytes, utf8ToBytes } from '@noble/hashes/utils.js';
import { CryptoError, dh, kdfPqxdh } from './primitives';
import {
  type RatchetState,
  initInitiator,
  initResponder,
  ratchetDecrypt,
  ratchetEncrypt
} from './ratchet';
import { MLKEM768_PUBLIC_KEY_BYTES, b64decode, b64encode } from './wire';

export const ENVELOPE_MESSAGE = 0x01;
export const ENVELOPE_PREKEY = 0x02;
export const KEM_CIPHERTEXT_BYTES = 1088;
const PREKEY_HEADER_BYTES = 1 + 32 * 3 + 4 + 4 + 1 + 1 + 4 + KEM_CIPHERTEXT_BYTES;
const AD_LABEL = utf8ToBytes('relay-e2ee-v1/ad\u0000');
const PQXDH_PREFIX = new Uint8Array(32).fill(0xff);
const AD_BYTES = AD_LABEL.length + 32 * 4;
const MLKEM768_SECRET_KEY_BYTES = 2400;
/** Plaintexts are padded to multiples of this, hiding exact message length. */
export const PADDING_BLOCK = 160;

/** A peer device's keys, already verified against its account identity (keys.verifyDevice). */
export interface PeerBundle {
  identityKey: string;
  agreementKey: string;
  signedPrekey: { key_id: number; public_key: string };
  pqPrekey: { key_id: number; public_key: string; oneTime: boolean };
  oneTimePrekey?: { key_id: number; public_key: string } | null;
}

export interface LocalIdentity {
  identityKey: string;
  agreement: { pub: string; priv: string };
}

/** Lookup of this device's prekey private keys by id (current and recent). */
export interface PrekeySecrets {
  signedPrekey(id: number): { pub: string; priv: string } | null;
  pqPrekey(id: number, oneTime: boolean): string | null;
  oneTimePrekey(id: number): string | null;
}

interface PrekeyHeader {
  senderIdentityKey: Uint8Array;
  senderAgreementKey: Uint8Array;
  ephemeral: Uint8Array;
  signedPrekeyId: number;
  pqPrekeyId: number;
  pqOneTime: boolean;
  oneTimePrekeyId: number | null;
  kemCiphertext: Uint8Array;
}

export interface Session {
  version: 1;
  role: 'initiator' | 'responder';
  associatedData: string;
  /** Ephemeral (base) key of the PQXDH run that created the session. */
  baseKey: string;
  ratchet: RatchetState;
  /** Encoded prekey header, re-sent until the peer replies (initiator only). */
  pendingPrekey: string | null;
  createdAt: number;
}

export interface Consumed {
  oneTimePrekeyId: number | null;
  pqOneTimePrekeyId: number | null;
}

// ------------------------------------------------------------------ padding

export function pad(plaintext: Uint8Array): Uint8Array {
  const length = Math.ceil((plaintext.length + 1) / PADDING_BLOCK) * PADDING_BLOCK;
  const out = new Uint8Array(length);
  out.set(plaintext);
  out[plaintext.length] = 0x80;
  return out;
}

export function unpad(padded: Uint8Array): Uint8Array {
  for (let i = padded.length - 1; i >= 0; i -= 1) {
    if (padded[i] === 0x80) return padded.slice(0, i);
    if (padded[i] !== 0) break;
  }
  throw new CryptoError('bad padding');
}

// --------------------------------------------------------- prekey header IO

function encodePrekeyHeader(header: PrekeyHeader): Uint8Array {
  const out = new Uint8Array(PREKEY_HEADER_BYTES);
  const view = new DataView(out.buffer);
  out[0] = ENVELOPE_PREKEY;
  out.set(header.senderIdentityKey, 1);
  out.set(header.senderAgreementKey, 33);
  out.set(header.ephemeral, 65);
  view.setUint32(97, header.signedPrekeyId, false);
  view.setUint32(101, header.pqPrekeyId, false);
  out[105] = header.pqOneTime ? 1 : 0;
  out[106] = header.oneTimePrekeyId === null ? 0 : 1;
  view.setUint32(107, header.oneTimePrekeyId ?? 0, false);
  out.set(header.kemCiphertext, 111);
  return out;
}

function decodePrekeyHeader(bytes: Uint8Array): PrekeyHeader {
  if (bytes.length < PREKEY_HEADER_BYTES || bytes[0] !== ENVELOPE_PREKEY) {
    throw new CryptoError('bad prekey envelope');
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const flags = [bytes[105], bytes[106]];
  if (flags.some((flag) => flag > 1)) throw new CryptoError('bad prekey envelope flags');
  return {
    senderIdentityKey: bytes.slice(1, 33),
    senderAgreementKey: bytes.slice(33, 65),
    ephemeral: bytes.slice(65, 97),
    signedPrekeyId: view.getUint32(97, false),
    pqPrekeyId: view.getUint32(101, false),
    pqOneTime: bytes[105] === 1,
    oneTimePrekeyId: bytes[106] === 1 ? view.getUint32(107, false) : null,
    kemCiphertext: bytes.slice(111, PREKEY_HEADER_BYTES)
  };
}

function associatedData(
  initiatorIdentity: Uint8Array,
  initiatorAgreement: Uint8Array,
  responderIdentity: Uint8Array,
  responderAgreement: Uint8Array
): Uint8Array {
  return concatBytes(AD_LABEL, initiatorIdentity, initiatorAgreement, responderIdentity, responderAgreement);
}

const k32 = (value: string, what: string) => b64decode(value, 32, what);

// ----------------------------------------------------------------- sessions

/** Run PQXDH as initiator against a (verified) peer bundle and open a session. */
export function startSession(local: LocalIdentity, peer: PeerBundle): Session {
  const identityA = k32(local.identityKey, 'identity key');
  const agreementA = k32(local.agreement.pub, 'agreement key');
  const agreementPrivA = k32(local.agreement.priv, 'agreement private key');
  const identityB = k32(peer.identityKey, 'peer identity key');
  const agreementB = k32(peer.agreementKey, 'peer agreement key');
  const signedPrekeyB = k32(peer.signedPrekey.public_key, 'peer signed prekey');
  const pqPrekeyB = b64decode(peer.pqPrekey.public_key, MLKEM768_PUBLIC_KEY_BYTES, 'peer pq prekey');

  const ephemeral = x25519.keygen();
  const parts = [
    PQXDH_PREFIX,
    dh(agreementPrivA, signedPrekeyB),
    dh(ephemeral.secretKey, agreementB),
    dh(ephemeral.secretKey, signedPrekeyB)
  ];
  if (peer.oneTimePrekey) {
    parts.push(dh(ephemeral.secretKey, k32(peer.oneTimePrekey.public_key, 'peer one-time prekey')));
  }
  const { cipherText, sharedSecret } = ml_kem768.encapsulate(pqPrekeyB);
  parts.push(sharedSecret);
  const sharedKey = kdfPqxdh(concatBytes(...parts));

  const header = encodePrekeyHeader({
    senderIdentityKey: identityA,
    senderAgreementKey: agreementA,
    ephemeral: ephemeral.publicKey,
    signedPrekeyId: peer.signedPrekey.key_id,
    pqPrekeyId: peer.pqPrekey.key_id,
    pqOneTime: peer.pqPrekey.oneTime,
    oneTimePrekeyId: peer.oneTimePrekey?.key_id ?? null,
    kemCiphertext: cipherText
  });
  return {
    version: 1,
    role: 'initiator',
    associatedData: b64encode(associatedData(identityA, agreementA, identityB, agreementB)),
    baseKey: b64encode(ephemeral.publicKey),
    ratchet: initInitiator(sharedKey, signedPrekeyB),
    pendingPrekey: b64encode(header),
    createdAt: Date.now()
  };
}

/** Encrypt one plaintext for the session's peer device. */
export function encrypt(session: Session, plaintext: Uint8Array): { session: Session; envelope: Uint8Array } {
  const { state, message } = ratchetEncrypt(
    session.ratchet,
    pad(plaintext),
    b64decode(session.associatedData, AD_BYTES, 'associated data')
  );
  const inner = concatBytes(new Uint8Array([ENVELOPE_MESSAGE]), message);
  const envelope = session.pendingPrekey
    ? concatBytes(b64decode(session.pendingPrekey, PREKEY_HEADER_BYTES, 'prekey header'), inner)
    : inner;
  return { session: { ...session, ratchet: state }, envelope };
}

export function envelopeKind(envelope: Uint8Array): 'prekey' | 'message' {
  if (envelope[0] === ENVELOPE_PREKEY) return 'prekey';
  if (envelope[0] === ENVELOPE_MESSAGE) return 'message';
  throw new CryptoError('unknown envelope type');
}

function decryptInner(session: Session, inner: Uint8Array): { session: Session; plaintext: Uint8Array } {
  if (inner[0] !== ENVELOPE_MESSAGE) throw new CryptoError('bad inner message');
  const ad = b64decode(session.associatedData, AD_BYTES, 'associated data');
  const { state, plaintext } = ratchetDecrypt(session.ratchet, inner.slice(1), ad);
  // Any successfully decrypted reply proves the peer has the session.
  return { session: { ...session, ratchet: state, pendingPrekey: null }, plaintext: unpad(plaintext) };
}

/**
 * Decrypt an envelope from a peer device.
 *
 * `expectedSender` must come from the verified directory (keys.verifyDevice);
 * a prekey message claiming different keys is rejected. `existing` is the
 * current session with that device, if any. On success the caller must store
 * the returned session and delete the `consumed` one-time private keys.
 */
export function decrypt(
  local: LocalIdentity,
  secrets: PrekeySecrets,
  existing: Session | null,
  envelope: Uint8Array,
  expectedSender: { identityKey: string; agreementKey: string }
): { session: Session; plaintext: Uint8Array; consumed: Consumed } {
  const none: Consumed = { oneTimePrekeyId: null, pqOneTimePrekeyId: null };
  if (envelopeKind(envelope) === 'message') {
    if (!existing) throw new CryptoError('no session for message');
    return { ...decryptInner(existing, envelope), consumed: none };
  }

  const header = decodePrekeyHeader(envelope);
  const inner = envelope.slice(PREKEY_HEADER_BYTES);
  if (
    b64encode(header.senderIdentityKey) !== expectedSender.identityKey ||
    b64encode(header.senderAgreementKey) !== expectedSender.agreementKey
  ) {
    throw new CryptoError('prekey message sender keys do not match the directory');
  }
  // A repeated prekey header for a session we already have: just continue it.
  if (existing && existing.baseKey === b64encode(header.ephemeral)) {
    return { ...decryptInner(existing, inner), consumed: none };
  }

  const signedPrekey = secrets.signedPrekey(header.signedPrekeyId);
  const pqSecret = secrets.pqPrekey(header.pqPrekeyId, header.pqOneTime);
  const oneTime = header.oneTimePrekeyId === null ? null : secrets.oneTimePrekey(header.oneTimePrekeyId);
  if (!signedPrekey || !pqSecret || (header.oneTimePrekeyId !== null && !oneTime)) {
    throw new CryptoError('unknown or already used prekey');
  }

  const agreementPrivB = k32(local.agreement.priv, 'agreement private key');
  const signedPrivB = k32(signedPrekey.priv, 'signed prekey private key');
  const parts = [
    PQXDH_PREFIX,
    dh(signedPrivB, header.senderAgreementKey),
    dh(agreementPrivB, header.ephemeral),
    dh(signedPrivB, header.ephemeral)
  ];
  if (oneTime) parts.push(dh(k32(oneTime, 'one-time prekey private key'), header.ephemeral));
  let kemSecret: Uint8Array;
  try {
    kemSecret = ml_kem768.decapsulate(header.kemCiphertext, b64decode(pqSecret, MLKEM768_SECRET_KEY_BYTES, 'pq secret'));
  } catch {
    throw new CryptoError('KEM decapsulation failed');
  }
  parts.push(kemSecret);
  const sharedKey = kdfPqxdh(concatBytes(...parts));

  const fresh: Session = {
    version: 1,
    role: 'responder',
    associatedData: b64encode(
      associatedData(
        header.senderIdentityKey,
        header.senderAgreementKey,
        k32(local.identityKey, 'identity key'),
        k32(local.agreement.pub, 'agreement key')
      )
    ),
    baseKey: b64encode(header.ephemeral),
    ratchet: initResponder(sharedKey, signedPrekey),
    pendingPrekey: null,
    createdAt: Date.now()
  };
  // Authenticates the whole PQXDH run: a wrong key anywhere fails here.
  const result = decryptInner(fresh, inner);
  return {
    ...result,
    consumed: {
      oneTimePrekeyId: header.oneTimePrekeyId,
      pqOneTimePrekeyId: header.pqOneTime ? header.pqPrekeyId : null
    }
  };
}
