import { describe, expect, it } from 'vitest';
import {
  generateAgreementKey,
  generateIdentity,
  generatePqKey,
  generateSigningKey,
  newDeviceId,
  pqPrekeyWire,
  signDevice,
  signedPrekeyWire
} from './keys';
import type { LocalDeviceState } from './keystore';
import {
  type ClaimedBundle,
  bundleFromClaim,
  consumePrekeys,
  decodePayload,
  encodePayload,
  localIdentity,
  prekeySecrets
} from './messaging';
import { CryptoError } from './primitives';
import { decrypt, encrypt, startSession } from './session';
import { WireError } from './wire';

/** A provisioned device, shaped like the keystore state the e2ee store keeps. */
function provision(userId: string): LocalDeviceState {
  const pqOneTime = generatePqKey();
  const oneTime = generateAgreementKey();
  return {
    userId,
    identity: generateIdentity(),
    device: {
      deviceId: newDeviceId(),
      signing: generateSigningKey(),
      agreement: generateAgreementKey(),
      signedPrekey: { id: 1, createdAt: 0, ...generateAgreementKey() },
      pqPrekey: { id: 2, createdAt: 0, ...generatePqKey() },
      oneTime: { 3: oneTime.priv },
      pqOneTime: { 4: pqOneTime.priv },
      nextKeyId: 5,
      registered: true,
      // Public halves, kept here only so the test can play the server.
      ...({ _public: { oneTime: oneTime.pub, pqOneTime: pqOneTime.pub } } as object)
    }
  };
}

/** What POST /e2ee/users/{id}/devices/{id}/claim returns for a device. */
function claimFor(state: LocalDeviceState): ClaimedBundle {
  const device = state.device!;
  const pub = (device as unknown as { _public: { oneTime: string; pqOneTime: string } })._public;
  return {
    user_id: state.userId,
    identity_key: state.identity.pub,
    device: {
      device_id: device.deviceId,
      signing_key: device.signing.pub,
      agreement_key: device.agreement.pub,
      identity_signature: signDevice(state.identity, state.userId, device.deviceId, device.signing, device.agreement),
      signed_prekey: signedPrekeyWire(device.signing, device.deviceId, device.signedPrekey),
      pq_prekey: pqPrekeyWire(device.signing, device.deviceId, device.pqPrekey)
    },
    one_time_prekey: { key_id: 3, public_key: pub.oneTime },
    pq_one_time_prekey: pqPrekeyWire(device.signing, device.deviceId, {
      id: 4,
      createdAt: 0,
      pub: pub.pqOneTime,
      priv: device.pqOneTime[4]
    })
  };
}

describe('E2EE messaging glue', () => {
  it('delivers a message from a server claim through to the recipient, consuming one-time keys', () => {
    const alice = provision('alice');
    const bob = provision('bob');

    const bundle = bundleFromClaim(claimFor(bob), 'bob', bob.identity.pub);
    expect(bundle.pqPrekey.oneTime).toBe(true);
    const session = startSession(localIdentity(alice), bundle);
    const { envelope } = encrypt(session, encodePayload({ v: 1, text: 'hello bob', reply_to_id: null }));

    const result = decrypt(localIdentity(bob), prekeySecrets(bob), null, envelope, {
      identityKey: alice.identity.pub,
      agreementKey: alice.device!.agreement.pub
    });
    expect(decodePayload(result.plaintext)).toEqual({ v: 1, text: 'hello bob', reply_to_id: null });

    expect(consumePrekeys(bob, result.consumed)).toBe(true);
    expect(bob.device!.oneTime).toEqual({});
    expect(bob.device!.pqOneTime).toEqual({});
    // A replayed first message can no longer set up a session on the same keys.
    expect(() =>
      decrypt(localIdentity(bob), prekeySecrets(bob), null, envelope, {
        identityKey: alice.identity.pub,
        agreementKey: alice.device!.agreement.pub
      })
    ).toThrow(CryptoError);
  });

  it('rejects claims that do not match the verified identity', () => {
    const bob = provision('bob');
    const claim = claimFor(bob);
    expect(() => bundleFromClaim(claim, 'bob', generateIdentity().pub)).toThrow(CryptoError);
    expect(() => bundleFromClaim({ ...claim, user_id: 'mallory' }, 'bob', bob.identity.pub)).toThrow(CryptoError);
  });

  it('rejects a server-substituted PQ one-time prekey', () => {
    const bob = provision('bob');
    const claim = claimFor(bob);
    const forged = pqPrekeyWire(generateSigningKey(), bob.device!.deviceId, {
      id: 4,
      createdAt: 0,
      ...generatePqKey()
    });
    expect(() => bundleFromClaim({ ...claim, pq_one_time_prekey: forged }, 'bob', bob.identity.pub)).toThrow(WireError);
  });

  it('falls back to the last-resort PQ prekey when one-time keys ran out', () => {
    const bob = provision('bob');
    const claim = { ...claimFor(bob), one_time_prekey: null, pq_one_time_prekey: null };
    const bundle = bundleFromClaim(claim, 'bob', bob.identity.pub);
    expect(bundle.pqPrekey).toMatchObject({ key_id: 2, oneTime: false });
    expect(bundle.oneTimePrekey).toBeNull();
  });

  it('validates decrypted payloads strictly', () => {
    const bytes = (value: unknown) => new TextEncoder().encode(JSON.stringify(value));
    expect(() => decodePayload(bytes({ v: 2, text: 'x' }))).toThrow(CryptoError);
    expect(() => decodePayload(bytes({ v: 1, text: 5 }))).toThrow(CryptoError);
    expect(() => decodePayload(bytes({ v: 1, text: 'x'.repeat(4001) }))).toThrow(CryptoError);
    expect(() => decodePayload(new Uint8Array([0xff, 0xfe]))).toThrow(CryptoError);
    expect(decodePayload(bytes({ v: 1, text: 'ok', extra: 'ignored' }))).toEqual({ v: 1, text: 'ok', reply_to_id: null });
  });

  it('uses the previous signed prekey after rotation', () => {
    const bob = provision('bob');
    const old = bob.device!.signedPrekey;
    bob.device!.previousSignedPrekey = old;
    bob.device!.signedPrekey = { id: 9, createdAt: 1, ...generateAgreementKey() };
    expect(prekeySecrets(bob).signedPrekey(1)).toEqual(old);
    expect(prekeySecrets(bob).signedPrekey(9)).not.toBeNull();
    expect(prekeySecrets(bob).signedPrekey(8)).toBeNull();
  });
});
