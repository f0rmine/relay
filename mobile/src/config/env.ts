const DEFAULT_API_BASE_URL = 'http://localhost:8000';

function normalizeBaseUrl(value: string, protocols: readonly string[], name: string): string {
  let url: URL;
  try {
    url = new URL(value.trim());
  } catch {
    throw new Error(`${name} must be an absolute URL`);
  }
  if (!protocols.includes(url.protocol)) {
    throw new Error(`${name} must use ${protocols.join(' or ')}`);
  }
  if (url.search || url.hash) {
    throw new Error(`${name} must not include a query string or fragment`);
  }
  return url.toString().replace(/\/+$/, '');
}

export const API_BASE_URL = normalizeBaseUrl(
  import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL,
  ['http:', 'https:'],
  'VITE_API_BASE_URL'
);

const defaultWebSocketUrl = API_BASE_URL.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:');

export const WS_BASE_URL = normalizeBaseUrl(
  import.meta.env.VITE_WS_BASE_URL || defaultWebSocketUrl,
  ['ws:', 'wss:'],
  'VITE_WS_BASE_URL'
);

export function apiUrl(path: string): string {
  return `${API_BASE_URL}/${path.replace(/^\/+/, '')}`;
}

export function webSocketUrl(path: string): string {
  return `${WS_BASE_URL}/${path.replace(/^\/+/, '')}`;
}

export function absoluteUrl(path?: string | null): string | undefined {
  if (!path) return undefined;
  if (/^https?:\/\//i.test(path)) return path;
  return apiUrl(path);
}
