import { API_BASE_URL } from '@/config/env';
import type { TokenResponse } from '@/api/types';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function errorMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object' && 'msg' in item) return String(item.msg);
        return null;
      })
      .filter(Boolean)
      .join('; ') || 'Request failed';
  }
  return 'Request failed';
}

function notifyTokensRefreshed(tokens: TokenResponse) {
  window.dispatchEvent(new CustomEvent('relay:tokens-refreshed', { detail: tokens }));
}

function notifyAuthExpired() {
  localStorage.removeItem('accessToken');
  localStorage.removeItem('refreshToken');
  localStorage.removeItem('authUser');
  window.dispatchEvent(new CustomEvent('relay:auth-expired'));
}

let refreshPromise: Promise<TokenResponse | null> | null = null;

function storeTokens(tokens: TokenResponse) {
  localStorage.setItem('accessToken', tokens.access_token);
  localStorage.setItem('refreshToken', tokens.refresh_token);
  localStorage.setItem('authUser', JSON.stringify(tokens.user));
  notifyTokensRefreshed(tokens);
}

async function refreshTokens(): Promise<TokenResponse | null> {
  if (refreshPromise) return refreshPromise;
  const refreshToken = localStorage.getItem('refreshToken');
  if (!refreshToken) return null;

  refreshPromise = (async () => {
    const refreshResponse = await safeFetch('/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken })
    });
    if (!refreshResponse.ok) {
      notifyAuthExpired();
      return null;
    }
    const refreshed = (await refreshResponse.json()) as TokenResponse;
    storeTokens(refreshed);
    return refreshed;
  })().finally(() => {
    refreshPromise = null;
  });

  return refreshPromise;
}

async function safeFetch(path: string, options: RequestInit): Promise<Response> {
  try {
    return await fetch(`${API_BASE_URL}${path}`, options);
  } catch {
    throw new ApiError(
      0,
      `Cannot reach backend at ${API_BASE_URL}. Check the server, Tailscale/LAN IP, and mobile .env URL.`
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
  const accessToken = localStorage.getItem('accessToken');
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
    if (response.status === 401) notifyAuthExpired();
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, errorMessage(body.detail));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function apiBlob(path: string): Promise<Blob> {
  const headers = new Headers();
  const accessToken = localStorage.getItem('accessToken');
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
    if (response.status === 401) notifyAuthExpired();
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, errorMessage(body.detail));
  }
  return response.blob();
}
