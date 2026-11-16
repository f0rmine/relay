import { describe, expect, it } from 'vitest';
import { generateIdentity } from './keys';
import { displayableFingerprint, groupDigits, safetyNumber } from './safety-number';

describe('safety numbers', () => {
  const alice = { identityKey: generateIdentity().pub, userId: 'alice-id' };
  const bob = { identityKey: generateIdentity().pub, userId: 'bob-id' };

  it('is 60 digits and identical from both sides', () => {
    const fromAlice = safetyNumber(alice, bob);
    expect(fromAlice).toMatch(/^\d{60}$/);
    expect(safetyNumber(bob, alice)).toBe(fromAlice);
    expect(groupDigits(fromAlice)).toHaveLength(12);
  });

  it('changes when either identity key changes', () => {
    const before = safetyNumber(alice, bob);
    const rekeyed = { ...bob, identityKey: generateIdentity().pub };
    expect(safetyNumber(alice, rekeyed)).not.toBe(before);
  });

  it('binds the user id, not only the key', () => {
    expect(displayableFingerprint(alice.identityKey, 'alice-id')).not.toBe(
      displayableFingerprint(alice.identityKey, 'mallory-id')
    );
  });

  it('is deterministic for a fixed key (pinned vector)', () => {
    // Identity key from the shared wire vector (Ed25519 seed 0x01 * 32).
    const fp = displayableFingerprint('iojj3XQJ8ZX9UtstPLpdcspnCb8dlBIb83SIAbQPb1w', 'user-1');
    expect(fp).toMatch(/^\d{30}$/);
    expect(displayableFingerprint('iojj3XQJ8ZX9UtstPLpdcspnCb8dlBIb83SIAbQPb1w', 'user-1')).toBe(fp);
  });
});
