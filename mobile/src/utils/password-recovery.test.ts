import { describe, expect, it } from 'vitest';
import {
  resetTokenFromDeepLink,
  resetTokenFromQuery,
  validateNewPassword
} from './password-recovery';

describe('password recovery helpers', () => {
  it('normalizes a reset token from router query values', () => {
    expect(resetTokenFromQuery('  reset-token  ')).toBe('reset-token');
    expect(resetTokenFromQuery(['first-token', 'second-token'])).toBe('first-token');
    expect(resetTokenFromQuery(null)).toBe('');
  });

  it('extracts tokens only from supported password-reset deep links', () => {
    expect(resetTokenFromDeepLink('relay://reset-password?token=reset%2Btoken')).toBe(
      'reset+token'
    );
    expect(
      resetTokenFromDeepLink('https://relay.example.com/reset-password?token=https-token')
    ).toBe('https-token');
    expect(resetTokenFromDeepLink('relay://conversation?token=secret')).toBeNull();
    expect(resetTokenFromDeepLink('https://relay.example.com/other?token=secret')).toBeNull();
    expect(resetTokenFromDeepLink('https://relay.example.com/reset-password')).toBeNull();
  });

  it('rejects ambiguous or oversized deep-link tokens', () => {
    expect(
      resetTokenFromDeepLink(
        'relay://reset-password?token=first&token=second'
      )
    ).toBeNull();
    expect(
      resetTokenFromDeepLink(`relay://reset-password?token=${'x'.repeat(4097)}`)
    ).toBeNull();
  });

  it('validates password presence and length', () => {
    expect(validateNewPassword('', '')).toBe('required');
    expect(validateNewPassword('short', 'short')).toBe('length');
    expect(validateNewPassword('x'.repeat(129), 'x'.repeat(129))).toBe('length');
  });

  it('requires matching passwords', () => {
    expect(validateNewPassword('password-one', 'password-two')).toBe('mismatch');
    expect(validateNewPassword('password-one', 'password-one')).toBeNull();
  });
});
