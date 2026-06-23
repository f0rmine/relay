import { API_BASE_URL, apiUrl } from '@/config/env';
import type { TokenResponse } from '@/api/types';
import { translate } from '@/i18n';
import {
  clearAuthTokens,
  getAccessToken,
  getRefreshToken,
  setAuthTokens,
  setStoredAuthUser
} from '@/services/auth-storage';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const backendErrorKeys: Record<string, string> = {
  'Missing bearer token': 'api.errors.missingAuth',
  'Missing token': 'api.errors.missingAuth',
  'User not found': 'api.errors.userNotFound',
  'Token expired': 'api.errors.tokenExpired',
  'Invalid token': 'api.errors.invalidToken',
  'Invalid token type': 'api.errors.invalidToken',
  'Invalid credentials': 'api.errors.invalidCredentials',
  'Invalid refresh token': 'api.errors.invalidToken',
  'Invalid reset token': 'api.errors.invalidResetToken',
  'Too many attempts, try again later': 'api.errors.tooManyAttempts',
  'Username already exists': 'api.errors.usernameExists',
  'Email already exists': 'api.errors.emailExists',
  'Display name is required': 'api.errors.displayNameRequired',
  'Conversation not found': 'api.errors.conversationNotFound',
  'Cannot create conversation with yourself': 'api.errors.selfConversation',
  'Message text or attachment is required': 'api.errors.emptyMessage',
  'Invalid attachment': 'api.errors.invalidAttachment',
  'Message not found': 'api.errors.messageNotFound',
  'Only sender can delete this message': 'api.errors.deleteForbidden',
  'Unsupported file type': 'api.errors.unsupportedFileType',
  'File extension does not match file type': 'api.errors.fileTypeMismatch',
  'Empty file upload': 'api.errors.emptyFile',
  'File is too large': 'api.errors.fileTooLarge',
  'Image content does not match file type': 'api.errors.imageTypeMismatch',
  'File missing from storage': 'api.errors.fileMissing',
  'Attachment not found': 'api.errors.attachmentNotFound',
  'Empty avatar upload': 'api.errors.emptyAvatar',
  'Unsupported avatar image type': 'api.errors.unsupportedAvatarType',
  'Avatar extension does not match file type': 'api.errors.avatarTypeMismatch',
  'Avatar content does not match file type': 'api.errors.avatarContentMismatch',
  'Avatar is too large': 'api.errors.avatarTooLarge'
};

function localizeBackendError(message: string): string {
  const normalized = message.replace(/^Value error,\s*/, '');
  const key = backendErrorKeys[normalized];
  return key ? translate(key) : message;
}

function errorMessage(detail: unknown): string {
  if (typeof detail === 'string') return localizeBackendError(detail);
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return localizeBackendError(item);
        if (item && typeof item === 'object' && 'msg' in item) {
          return localizeBackendError(String(item.msg));
        }
        return null;
      })
      .filter(Boolean)
      .join('; ') || translate('api.requestFailed');
  }
  return translate('api.requestFailed');
}

function notifyTokensRefreshed(tokens: TokenResponse) {
  window.dispatchEvent(new CustomEvent('relay:tokens-refreshed', { detail: tokens }));
}

async function notifyAuthExpired() {
  try {
    await Promise.all([clearAuthTokens(), setStoredAuthUser(null)]);
  } finally {
    window.dispatchEvent(new CustomEvent('relay:auth-expired'));
  }
}

let refreshPromise: Promise<TokenResponse | null> | null = null;

async function storeTokens(tokens: TokenResponse) {
  try {
    await Promise.all([
      setAuthTokens(tokens.access_token, tokens.refresh_token),
      setStoredAuthUser(tokens.user)
    ]);
  } catch (error) {
    await Promise.allSettled([clearAuthTokens(), setStoredAuthUser(null)]);
    throw error;
  }
  notifyTokensRefreshed(tokens);
}

async function refreshTokens(): Promise<TokenResponse | null> {
  if (refreshPromise) return refreshPromise;
  const refreshToken = await getRefreshToken();
  if (!refreshToken) return null;

  refreshPromise = (async () => {
    const refreshResponse = await safeFetch('/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken })
    });
    if (!refreshResponse.ok) {
      await notifyAuthExpired();
      return null;
    }
    const refreshed = (await refreshResponse.json()) as TokenResponse;
    await storeTokens(refreshed);
    return refreshed;
  })().finally(() => {
    refreshPromise = null;
  });

  return refreshPromise;
}

async function safeFetch(path: string, options: RequestInit): Promise<Response> {
  try {
    return await fetch(apiUrl(path), options);
  } catch {
    throw new ApiError(
      0,
      translate('api.cannotReach', { url: API_BASE_URL })
    );
  }
}

export function displayError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  const accessToken = await getAccessToken();
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }

  let response = await safeFetch(path, { ...options, headers });
  if (response.status === 401) {
    const refreshed = await refreshTokens();
    if (refreshed) {
      headers.set('Authorization', `Bearer ${refreshed.access_token}`);
      response = await safeFetch(path, { ...options, headers });
    }
  }

  if (!response.ok) {
    if (response.status === 401) await notifyAuthExpired();
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, errorMessage(body.detail));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function apiBlob(path: string): Promise<Blob> {
  const headers = new Headers();
  const accessToken = await getAccessToken();
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }

  let response = await safeFetch(path, { headers });
  if (response.status === 401) {
    const refreshed = await refreshTokens();
    if (refreshed) {
      headers.set('Authorization', `Bearer ${refreshed.access_token}`);
      response = await safeFetch(path, { headers });
    }
  }

  if (!response.ok) {
    if (response.status === 401) await notifyAuthExpired();
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, errorMessage(body.detail));
  }
  return response.blob();
}
