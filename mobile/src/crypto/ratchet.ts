/**
 * Double Ratchet (Signal specification, revision 4), without header encryption.
 *
 * All functions are pure: they take a state and return a new one. Decryption
 * works on a copy and only returns the advanced state if authentication
 * succeeds, so a forged or corrupted message can never damage a session.
 */
import { x25519 } from '@noble/curves/ed25519.js';
import { concatBytes } from '@noble/hashes/utils.js';
import { CryptoError, dh, kdfChain, kdfRoot, open, seal } from './primitives';
import { b64decode, b64encode } from './wire';

/** Max message keys skipped in one chain step (spec's MAX_SKIP). */
export const MAX_SKIP = 1000;
/** Max skipped keys kept across the whole session; oldest are evicted. */
export const MAX_SKIPPED_TOTAL = 2000;
export const HEADER_BYTES = 40;

export interface RatchetState {
  rootKey: string;
  sendChain: string | null;
  receiveChain: string | null;
  dhSelf: { pub: string; priv: string };
  dhRemote: string | null;
  sendCount: number;
  receiveCount: number;
  previousSendCount: number;
  /** [`${remoteDhPub}:${n}`, messageKey] in insertion order, for eviction. */
  skipped: Array<[string, string]>;
}

export interface Header {
  dh: Uint8Array;
  previousCount: number;
  count: number;
}

const key32 = (value: string, what: string) => b64decode(value, 32, what);

function keyPair() {
  const { secretKey, publicKey } = x25519.keygen();
  return { pub: b64encode(publicKey), priv: b64encode(secretKey) };
}

export function encodeHeader(header: Header): Uint8Array {
  const out = new Uint8Array(HEADER_BYTES);
  out.set(header.dh, 0);
  const view = new DataView(out.buffer);
  view.setUint32(32, header.previousCount, false);
  view.setUint32(36, header.count, false);
  return out;
}

export function decodeHeader(bytes: Uint8Array): Header {
  if (bytes.length !== HEADER_BYTES) throw new CryptoError('bad ratchet header');
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  return { dh: bytes.slice(0, 32), previousCount: view.getUint32(32, false), count: view.getUint32(36, false) };
}

/** Initiator (sent the PQXDH prekey message): ratchets immediately against the peer's signed prekey. */
export function initInitiator(sharedKey: Uint8Array, remoteSignedPrekey: Uint8Array): RatchetState {
  const dhSelf = keyPair();
  const [rootKey, sendChain] = kdfRoot(sharedKey, dh(key32(dhSelf.priv, 'dh'), remoteSignedPrekey));
  return {
    rootKey: b64encode(rootKey),
    sendChain: b64encode(sendChain),
    receiveChain: null,
    dhSelf,
    dhRemote: b64encode(remoteSignedPrekey),
    sendCount: 0,
    receiveCount: 0,
    previousSendCount: 0,
    skipped: []
  };
}

/** Responder: starts from its signed prekey pair and waits for the first message. */
export function initResponder(sharedKey: Uint8Array, signedPrekey: { pub: string; priv: string }): RatchetState {
  return {
    rootKey: b64encode(sharedKey),
    sendChain: null,
    receiveChain: null,
    dhSelf: { ...signedPrekey },
    dhRemote: null,
    sendCount: 0,
    receiveCount: 0,
    previousSendCount: 0,
    skipped: []
  };
}

function clone(state: RatchetState): RatchetState {
  return { ...state, dhSelf: { ...state.dhSelf }, skipped: state.skipped.map(([k, v]) => [k, v]) };
}

export function ratchetEncrypt(
  state: RatchetState,
  plaintext: Uint8Array,
  associatedData: Uint8Array
): { state: RatchetState; message: Uint8Array } {
  if (!state.sendChain) throw new CryptoError('session cannot send before receiving');
  const next = clone(state);
  const [chain, messageKey] = kdfChain(key32(next.sendChain!, 'send chain'));
  const header = encodeHeader({
    dh: key32(next.dhSelf.pub, 'dh'),
    previousCount: next.previousSendCount,
    count: next.sendCount
  });
  next.sendChain = b64encode(chain);
  next.sendCount += 1;
  const ciphertext = seal(messageKey, plaintext, concatBytes(associatedData, header));
  return { state: next, message: concatBytes(header, ciphertext) };
}

function skipKeys(state: RatchetState, until: number): void {
  if (!state.receiveChain || !state.dhRemote) return;
  if (until - state.receiveCount > MAX_SKIP) throw new CryptoError('too many skipped messages');
  let chain = key32(state.receiveChain, 'receive chain');
  while (state.receiveCount < until) {
    const [nextChain, messageKey] = kdfChain(chain);
    state.skipped.push([`${state.dhRemote}:${state.receiveCount}`, b64encode(messageKey)]);
    chain = nextChain;
    state.receiveCount += 1;
  }
  state.receiveChain = b64encode(chain);
  if (state.skipped.length > MAX_SKIPPED_TOTAL) {
    state.skipped.splice(0, state.skipped.length - MAX_SKIPPED_TOTAL);
  }
}

function dhRatchet(state: RatchetState, header: Header): void {
  state.previousSendCount = state.sendCount;
  state.sendCount = 0;
  state.receiveCount = 0;
  state.dhRemote = b64encode(header.dh);
  const [rootAfterReceive, receiveChain] = kdfRoot(
    key32(state.rootKey, 'root'),
    dh(key32(state.dhSelf.priv, 'dh'), header.dh)
  );
  state.receiveChain = b64encode(receiveChain);
  state.dhSelf = keyPair();
  const [rootAfterSend, sendChain] = kdfRoot(rootAfterReceive, dh(key32(state.dhSelf.priv, 'dh'), header.dh));
  state.rootKey = b64encode(rootAfterSend);
  state.sendChain = b64encode(sendChain);
}

export function ratchetDecrypt(
  state: RatchetState,
  message: Uint8Array,
  associatedData: Uint8Array
): { state: RatchetState; plaintext: Uint8Array } {
  if (message.length < HEADER_BYTES + 16) throw new CryptoError('message too short');
  const headerBytes = message.slice(0, HEADER_BYTES);
  const header = decodeHeader(headerBytes);
  const ciphertext = message.slice(HEADER_BYTES);
  const aad = concatBytes(associatedData, headerBytes);
  const next = clone(state);

  const skippedId = `${b64encode(header.dh)}:${header.count}`;
  const skippedIndex = next.skipped.findIndex(([id]) => id === skippedId);
  if (skippedIndex >= 0) {
    const plaintext = open(key32(next.skipped[skippedIndex][1], 'skipped key'), ciphertext, aad);
    next.skipped.splice(skippedIndex, 1);
    return { state: next, plaintext };
  }

  if (next.dhRemote !== b64encode(header.dh)) {
    skipKeys(next, header.previousCount);
    dhRatchet(next, header);
  }
  skipKeys(next, header.count);
  const [chain, messageKey] = kdfChain(key32(next.receiveChain!, 'receive chain'));
  next.receiveChain = b64encode(chain);
  next.receiveCount += 1;
  return { state: next, plaintext: open(messageKey, ciphertext, aad) };
}
