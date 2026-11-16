import { ed25519 } from '@noble/curves/ed25519.js';
import { bytesToHex, utf8ToBytes } from '@noble/hashes/utils.js';
import { describe, expect, it } from 'vitest';
import { WireError, b64decode, b64encode, deviceMessage, prekeyMessage, SIGNED_PREKEY_LABEL } from './wire';

// Same pinned vector as backend/app/tests/test_e2ee.py::test_shared_wire_vector_matches_mobile_client
const identitySeed = new Uint8Array(32).fill(1);
const signingSeed = new Uint8Array(32).fill(2);
const agreement = Uint8Array.from({ length: 32 }, (_, i) => i);

describe('E2EE wire format', () => {
  it('matches the backend byte layout and signature', () => {
    const signingPub = ed25519.getPublicKey(signingSeed);
    const message = deviceMessage('user-1', 'device-abc', signingPub, agreement);
    expect(bytesToHex(message)).toBe(
      bytesToHex(utf8ToBytes('relay-e2ee-v1/device\u0000user-1\u0000device-abc\u0000')) +
        bytesToHex(signingPub) +
        bytesToHex(agreement)
    );
    expect(b64encode(signingPub)).toBe('gTl3Dqh9F19Wo1Rmw0x-zMuNipG07jeiXfYPW4_Js5Q');
    expect(b64encode(ed25519.getPublicKey(identitySeed))).toBe('iojj3XQJ8ZX9UtstPLpdcspnCb8dlBIb83SIAbQPb1w');
    expect(b64encode(ed25519.sign(message, identitySeed))).toBe(
      'FqLAJw0VUfiV5xmyLcjFVvlylblU97K1niafsUptGlrFKKNDuxlj3YChV_eXayJaRwbRhRk4RxiDDSR_KxBtDA'
    );
  });

  it('encodes prekey ids as 4-byte big-endian after the device id', () => {
    const message = prekeyMessage(SIGNED_PREKEY_LABEL, 'device-abc', 7, agreement);
    expect(Array.from(message.slice(-36, -32))).toEqual([0, 0, 0, 7]);
    expect(() => prekeyMessage(SIGNED_PREKEY_LABEL, 'd', -1, agreement)).toThrow(WireError);
    expect(() => prekeyMessage(SIGNED_PREKEY_LABEL, 'd', 2 ** 32, agreement)).toThrow(WireError);
  });

  it('round-trips base64url and rejects padding, junk and wrong lengths', () => {
    expect(b64decode(b64encode(agreement), 32, 'k')).toEqual(agreement);
    for (const bad of ['', 'AAAA=', 'A'.repeat(42), '%%%', 'ab+/']) {
      expect(() => b64decode(bad, 32, 'k')).toThrow(WireError);
    }
  });

  it('refuses NUL inside identifiers (would break field separation)', () => {
    expect(() => deviceMessage('a\u0000b', 'd', agreement, agreement)).toThrow(WireError);
  });
});
