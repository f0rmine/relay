import { describe, expect, it } from 'vitest';
import {
  type DeviceWire,
  generateAgreementKey,
  generateIdentity,
  generatePqKey,
  generateSigningKey,
  newDeviceId,
  pqPrekeyWire,
  signDevice,
  signedPrekeyWire,
  verifyDevice
} from './keys';
import { WireError } from './wire';

function makeDevice(userId = 'user-1') {
  const identity = generateIdentity();
  const signing = generateSigningKey();
  const agreement = generateAgreementKey();
  const deviceId = newDeviceId();
  const device: DeviceWire = {
    device_id: deviceId,
    signing_key: signing.pub,
    agreement_key: agreement.pub,
    identity_signature: signDevice(identity, userId, deviceId, signing, agreement),
    signed_prekey: signedPrekeyWire(signing, deviceId, { id: 1, createdAt: 0, ...generateAgreementKey() }),
    pq_prekey: pqPrekeyWire(signing, deviceId, { id: 2, createdAt: 0, ...generatePqKey() })
  };
  return { identity, device };
}

describe('device verification', () => {
  it('accepts a correctly signed device', () => {
    const { identity, device } = makeDevice();
    expect(() => verifyDevice(identity.pub, 'user-1', device)).not.toThrow();
    expect(device.device_id).toMatch(/^[A-Za-z0-9_-]{24}$/);
  });

  it('rejects a device vouched for by another identity (server-injected device)', () => {
    const { device } = makeDevice();
    expect(() => verifyDevice(generateIdentity().pub, 'user-1', device)).toThrow(WireError);
  });

  it('rejects a device signature replayed onto another account', () => {
    const { identity, device } = makeDevice('user-1');
    expect(() => verifyDevice(identity.pub, 'user-2', device)).toThrow(WireError);
  });

  it('rejects swapped agreement keys and forged prekeys', () => {
    const { identity, device } = makeDevice();
    expect(() =>
      verifyDevice(identity.pub, 'user-1', { ...device, agreement_key: generateAgreementKey().pub })
    ).toThrow(WireError);
    const otherSigner = generateSigningKey();
    const forged = signedPrekeyWire(otherSigner, device.device_id, { id: 1, createdAt: 0, ...generateAgreementKey() });
    expect(() => verifyDevice(identity.pub, 'user-1', { ...device, signed_prekey: forged })).toThrow(WireError);
    expect(() =>
      verifyDevice(identity.pub, 'user-1', {
        ...device,
        pq_prekey: { ...device.pq_prekey, key_id: device.pq_prekey.key_id + 1 }
      })
    ).toThrow(WireError);
  });
});
