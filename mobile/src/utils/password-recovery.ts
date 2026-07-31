import type { LocationQueryValue } from 'vue-router';

export type PasswordValidationError = 'required' | 'length' | 'mismatch';

export function resetTokenFromQuery(value: LocationQueryValue | LocationQueryValue[]): string {
  const token = Array.isArray(value) ? value[0] : value;
  return typeof token === 'string' ? token.trim() : '';
}

export function resetTokenFromDeepLink(value: string): string | null {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return null;
  }

  const customSchemeReset = (
    url.protocol === 'relay:'
    && url.hostname === 'reset-password'
    && (url.pathname === '' || url.pathname === '/')
  );
  const httpsReset = url.protocol === 'https:' && url.pathname === '/reset-password';
  if (!customSchemeReset && !httpsReset) return null;

  const tokens = url.searchParams.getAll('token');
  if (tokens.length !== 1) return null;
  const token = tokens[0].trim();
  return token && token.length <= 4096 ? token : null;
}

export function validateNewPassword(password: string, confirmation: string): PasswordValidationError | null {
  if (!password || !confirmation) return 'required';
  if (password.length < 8 || password.length > 128) return 'length';
  if (password !== confirmation) return 'mismatch';
  return null;
}
