import { utf8ToBytes } from '@noble/hashes/utils.js';
import { describe, expect, it } from 'vitest';
import { generateAgreementKey, generateIdentity, generatePqKey } from './keys';
import { CryptoError } from './primitives';
import { MAX_SKIP } from './ratchet';
import {
  type LocalIdentity,
  type PeerBundle,
  type PrekeySecrets,
  type Session,
  decrypt,
  encrypt,
  envelopeKind,
  pad,
  startSession,
  unpad
} from './session';

const text = (value: string) => utf8ToBytes(value);
const str = (bytes: Uint8Array) => new TextDecoder().decode(bytes);

/** A simulated device with prekeys, mirroring what the keystore holds. */
function makeDevice(options: { oneTime?: boolean; pqOneTime?: boolean } = {}) {
  const identity = generateIdentity();
  const agreement = generateAgreementKey();
  const signedPrekey = generateAgreementKey();
  const pqLastResort = generatePqKey();
  const pqOneTime = generatePqKey();
  const oneTime = generateAgreementKey();
  const used = { oneTime: false, pqOneTime: false };

  const local: LocalIdentity = { identityKey: identity.pub, agreement };
  const secrets: PrekeySecrets = {
    signedPrekey: (id) => (id === 1 ? signedPrekey : null),
    pqPrekey: (id, isOneTime) => {
      if (isOneTime) return id === 7 && !used.pqOneTime ? pqOneTime.priv : null;
      return id === 2 ? pqLastResort.priv : null;
    },
    oneTimePrekey: (id) => (id === 5 && !used.oneTime ? oneTime.priv : null)
  };
  const bundle: PeerBundle = {
    identityKey: identity.pub,
    agreementKey: agreement.pub,
    signedPrekey: { key_id: 1, public_key: signedPrekey.pub },
    pqPrekey: options.pqOneTime === false
      ? { key_id: 2, public_key: pqLastResort.pub, oneTime: false }
      : { key_id: 7, public_key: pqOneTime.pub, oneTime: true },
    oneTimePrekey: options.oneTime === false ? null : { key_id: 5, public_key: oneTime.pub }
  };
  const sender = { identityKey: identity.pub, agreementKey: agreement.pub };
  return { local, secrets, bundle, sender, used };
}

type Device = ReturnType<typeof makeDevice>;

/** Holds one side's session and applies the caller's bookkeeping like the app will. */
class Peer {
  session: Session | null = null;
  constructor(public device: Device) {}

  send(to: Device, message: string): Uint8Array {
    if (!this.session) this.session = startSession(this.device.local, to.bundle);
    const { session, envelope } = encrypt(this.session, text(message));
    this.session = session;
    return envelope;
  }

  receive(from: Device, envelope: Uint8Array): string {
    const result = decrypt(this.device.local, this.device.secrets, this.session, envelope, from.sender);
    this.session = result.session;
    if (result.consumed.oneTimePrekeyId !== null) this.device.used.oneTime = true;
    if (result.consumed.pqOneTimePrekeyId !== null) this.device.used.pqOneTime = true;
    return str(result.plaintext);
  }
}

function pair() {
  const aliceDevice = makeDevice();
  const bobDevice = makeDevice();
  return { alice: new Peer(aliceDevice), bob: new Peer(bobDevice), aliceDevice, bobDevice };
}

describe('PQXDH + Double Ratchet sessions', () => {
  it('runs a full conversation and drops the prekey header after the first reply', () => {
    const { alice, bob, aliceDevice, bobDevice } = pair();
    const first = alice.send(bobDevice, 'hi bob');
    const second = alice.send(bobDevice, 'still there?');
    expect(envelopeKind(first)).toBe('prekey');
    expect(envelopeKind(second)).toBe('prekey');

    expect(bob.receive(aliceDevice, first)).toBe('hi bob');
    expect(bob.receive(aliceDevice, second)).toBe('still there?');
    expect(bobDevice.used).toEqual({ oneTime: true, pqOneTime: true });

    const reply = bob.send(aliceDevice, 'hey alice');
    expect(envelopeKind(reply)).toBe('message');
    expect(alice.receive(bobDevice, reply)).toBe('hey alice');

    for (let round = 0; round < 5; round += 1) {
      const a = alice.send(bobDevice, `a${round}`);
      expect(envelopeKind(a)).toBe('message');
      expect(bob.receive(aliceDevice, a)).toBe(`a${round}`);
      expect(alice.receive(bobDevice, bob.send(aliceDevice, `b${round}`))).toBe(`b${round}`);
    }
  });

  it('handles out-of-order delivery across ratchet steps', () => {
    const { alice, bob, aliceDevice, bobDevice } = pair();
    const batch = ['m0', 'm1', 'm2', 'm3', 'm4'].map((m) => alice.send(bobDevice, m));
    expect(bob.receive(aliceDevice, batch[0])).toBe('m0');
    expect(bob.receive(aliceDevice, batch[4])).toBe('m4');
    expect(bob.receive(aliceDevice, batch[2])).toBe('m2');

    alice.receive(bobDevice, bob.send(aliceDevice, 'ack'));
    const later = alice.send(bobDevice, 'after ratchet');
    expect(bob.receive(aliceDevice, later)).toBe('after ratchet');
    // Keys skipped in the previous chain are still usable after the DH ratchet.
    expect(bob.receive(aliceDevice, batch[1])).toBe('m1');
    expect(bob.receive(aliceDevice, batch[3])).toBe('m3');
  });

  it('rejects replays', () => {
    const { alice, bob, aliceDevice, bobDevice } = pair();
    const first = alice.send(bobDevice, 'once');
    const second = alice.send(bobDevice, 'twice?');
    bob.receive(aliceDevice, first);
    bob.receive(aliceDevice, second);
    expect(() => bob.receive(aliceDevice, second)).toThrow(CryptoError);
  });

  it('rejects tampering without corrupting the session', () => {
    const { alice, bob, aliceDevice, bobDevice } = pair();
    bob.receive(aliceDevice, alice.send(bobDevice, 'setup'));
    alice.receive(bobDevice, bob.send(aliceDevice, 'ok'));

    const genuine = alice.send(bobDevice, 'genuine');
    for (const index of [1, 20, 40, genuine.length - 1]) {
      const forged = genuine.slice();
      forged[index] ^= 0x01;
      expect(() => bob.receive(aliceDevice, forged)).toThrow(CryptoError);
    }
    expect(bob.receive(aliceDevice, genuine)).toBe('genuine');
  });

  it('rejects a tampered ML-KEM ciphertext (hybrid secret is authenticated)', () => {
    const { alice, bob, aliceDevice, bobDevice } = pair();
    const envelope = alice.send(bobDevice, 'pq');
    const forged = envelope.slice();
    forged[500] ^= 0x01; // inside the 1088-byte KEM ciphertext
    expect(() => bob.receive(aliceDevice, forged)).toThrow(CryptoError);
    expect(bobDevice.used).toEqual({ oneTime: false, pqOneTime: false });
    expect(bob.receive(aliceDevice, envelope)).toBe('pq');
  });

  it('rejects prekey messages whose sender keys differ from the directory', () => {
    const { alice, bob, bobDevice } = pair();
    const mallory = makeDevice();
    const envelope = alice.send(bobDevice, 'who am i');
    expect(() => bob.receive(mallory, envelope)).toThrow(/do not match the directory/);
  });

  it('refuses a second session on an already consumed one-time prekey', () => {
    const { alice, bob, aliceDevice, bobDevice } = pair();
    bob.receive(aliceDevice, alice.send(bobDevice, 'first session'));
    const replayer = new Peer(aliceDevice); // same identity, fresh ephemeral, same old bundle
    const envelope = replayer.send(bobDevice, 'new session on used keys');
    expect(() => bob.receive(aliceDevice, envelope)).toThrow(/already used/);
  });

  it('works without one-time prekeys (last-resort PQ prekey)', () => {
    const aliceDevice = makeDevice();
    const bobDevice = makeDevice({ oneTime: false, pqOneTime: false });
    const alice = new Peer(aliceDevice);
    const bob = new Peer(bobDevice);
    expect(bob.receive(aliceDevice, alice.send(bobDevice, 'fallback'))).toBe('fallback');
    expect(bobDevice.used).toEqual({ oneTime: false, pqOneTime: false });
  });

  it('bounds skipped message keys', () => {
    const { alice, bob, aliceDevice, bobDevice } = pair();
    bob.receive(aliceDevice, alice.send(bobDevice, 'start'));
    alice.receive(bobDevice, bob.send(aliceDevice, 'ok'));
    let last: Uint8Array = new Uint8Array();
    for (let i = 0; i < MAX_SKIP + 2; i += 1) last = alice.send(bobDevice, `spam ${i}`);
    expect(() => bob.receive(aliceDevice, last)).toThrow(/too many skipped/);
  });

  it('recovers from state compromise after a round trip (post-compromise security)', () => {
    const { alice, bob, aliceDevice, bobDevice } = pair();
    bob.receive(aliceDevice, alice.send(bobDevice, 'setup'));
    alice.receive(bobDevice, bob.send(aliceDevice, 'ok'));

    const stolen = structuredClone(bob.session!); // attacker copies Bob's state
    bob.receive(aliceDevice, alice.send(bobDevice, 'ping'));
    alice.receive(bobDevice, bob.send(aliceDevice, 'pong'));

    const secret = alice.send(bobDevice, 'after healing');
    const attacker = new Peer(bobDevice);
    attacker.session = stolen;
    expect(() => attacker.receive(aliceDevice, secret)).toThrow(CryptoError);
    expect(bob.receive(aliceDevice, secret)).toBe('after healing');
  });

  it('survives JSON round-trips of session state', () => {
    const { alice, bob, aliceDevice, bobDevice } = pair();
    bob.receive(aliceDevice, alice.send(bobDevice, 'one'));
    alice.session = JSON.parse(JSON.stringify(alice.session));
    bob.session = JSON.parse(JSON.stringify(bob.session));
    expect(alice.receive(bobDevice, bob.send(aliceDevice, 'two'))).toBe('two');
    expect(bob.receive(aliceDevice, alice.send(bobDevice, 'three'))).toBe('three');
  });

  it('hides message length within a padding block', () => {
    const { alice, bob, aliceDevice, bobDevice } = pair();
    bob.receive(aliceDevice, alice.send(bobDevice, 'setup'));
    alice.receive(bobDevice, bob.send(aliceDevice, 'ok'));
    const short = alice.send(bobDevice, 'k');
    const longer = alice.send(bobDevice, 'x'.repeat(120));
    expect(short.length).toBe(longer.length);
    expect(unpad(pad(new Uint8Array([1, 0, 0x80])))).toEqual(new Uint8Array([1, 0, 0x80]));
    expect(() => unpad(new Uint8Array(160))).toThrow(CryptoError);
  });
});
