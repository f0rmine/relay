import type { LocationQueryValue } from 'vue-router';

export type PasswordValidationError = 'required' | 'length' | 'mismatch';

export function resetTokenFromQuery(value: LocationQueryValue | LocationQueryValue[]): string {
  const token = Array.isArray(value) ? value[0] : value;
  return typeof token === 'string' ? token.trim() : '';
}

export function validateNewPassword(password: string, confirmation: string): PasswordValidationError | null {
  if (!password || !confirmation) return 'required';
  if (password.length < 8 || password.length > 128) return 'length';
  if (password !== confirmation) return 'mismatch';
  return null;
}
