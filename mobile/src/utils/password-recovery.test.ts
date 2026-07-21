import { describe, expect, it } from 'vitest';
import { resetTokenFromQuery, validateNewPassword } from './password-recovery';

describe('password recovery helpers', () => {
  it('normalizes a reset token from router query values', () => {
    expect(resetTokenFromQuery('  reset-token  ')).toBe('reset-token');
    expect(resetTokenFromQuery(['first-token', 'second-token'])).toBe('first-token');
    expect(resetTokenFromQuery(null)).toBe('');
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
