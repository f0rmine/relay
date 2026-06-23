import { Capacitor } from '@capacitor/core';
import { SecureStorage } from '@aparajita/capacitor-secure-storage';
import type { User } from '@/api/types';

const ACCESS_TOKEN_KEY = 'accessToken';
const REFRESH_TOKEN_KEY = 'refreshToken';
const AUTH_USER_KEY = 'authUser';
const useSecureStorage = Capacitor.isNativePlatform();

export interface AuthTokens {
  accessToken: string | null;
  refreshToken: string | null;
}

let cachedTokens: AuthTokens | null = null;
let loadPromise: Promise<AuthTokens> | null = null;
let cachedUser: User | null | undefined;

function localTokens(): AuthTokens {
  return {
    accessToken: localStorage.getItem(ACCESS_TOKEN_KEY),
    refreshToken: localStorage.getItem(REFRESH_TOKEN_KEY)
  };
}

function removeLocalTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

function parseUser(value: unknown): User | null {
  if (typeof value !== 'string' || !value) return null;
  try {
    return JSON.parse(value) as User;
  } catch {
    return null;
  }
}

async function loadNativeTokens(): Promise<AuthTokens> {
  const legacy = localTokens();
  try {
    const [storedAccessToken, storedRefreshToken] = await Promise.all([
      SecureStorage.getItem(ACCESS_TOKEN_KEY),
      SecureStorage.getItem(REFRESH_TOKEN_KEY)
    ]);
    const accessToken = storedAccessToken ?? legacy.accessToken;
    const refreshToken = storedRefreshToken ?? legacy.refreshToken;

    const migrationKeys: string[] = [];
    if (!storedAccessToken && legacy.accessToken) {
      migrationKeys.push(ACCESS_TOKEN_KEY);
    }
    if (!storedRefreshToken && legacy.refreshToken) {
      migrationKeys.push(REFRESH_TOKEN_KEY);
    }
    try {
      await Promise.all(
        migrationKeys.map((key) =>
          SecureStorage.setItem(key, key === ACCESS_TOKEN_KEY ? legacy.accessToken! : legacy.refreshToken!)
        )
      );
    } catch (error) {
      await Promise.allSettled(migrationKeys.map((key) => SecureStorage.removeItem(key)));
      throw error;
    }

    return { accessToken, refreshToken };
  } finally {
    // Native credentials must never remain in plaintext after startup.
    removeLocalTokens();
  }
}

export async function getAuthTokens(): Promise<AuthTokens> {
  if (cachedTokens) return { ...cachedTokens };
  if (!loadPromise) {
    loadPromise = (useSecureStorage ? loadNativeTokens() : Promise.resolve(localTokens()))
      .then((tokens) => {
        cachedTokens = tokens;
        return tokens;
      })
      .finally(() => {
        loadPromise = null;
      });
  }
  return { ...(await loadPromise) };
}

export async function getAccessToken(): Promise<string | null> {
  return (await getAuthTokens()).accessToken;
}

export async function getRefreshToken(): Promise<string | null> {
  return (await getAuthTokens()).refreshToken;
}

export async function setAuthTokens(accessToken: string, refreshToken: string): Promise<void> {
  if (useSecureStorage) {
    try {
      await Promise.all([
        SecureStorage.setItem(ACCESS_TOKEN_KEY, accessToken),
        SecureStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
      ]);
    } catch (error) {
      cachedTokens = { accessToken: null, refreshToken: null };
      await Promise.allSettled([
        SecureStorage.removeItem(ACCESS_TOKEN_KEY),
        SecureStorage.removeItem(REFRESH_TOKEN_KEY)
      ]);
      throw error;
    } finally {
      removeLocalTokens();
    }
  } else {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  }
  cachedTokens = { accessToken, refreshToken };
}

export async function clearAuthTokens(): Promise<void> {
  cachedTokens = { accessToken: null, refreshToken: null };
  if (useSecureStorage) {
    try {
      await Promise.all([
        SecureStorage.removeItem(ACCESS_TOKEN_KEY),
        SecureStorage.removeItem(REFRESH_TOKEN_KEY)
      ]);
    } finally {
      removeLocalTokens();
    }
    return;
  }
  removeLocalTokens();
}

export async function getStoredAuthUser(): Promise<User | null> {
  if (cachedUser !== undefined) return cachedUser;
  const legacyUser = localStorage.getItem(AUTH_USER_KEY);
  if (!useSecureStorage) {
    cachedUser = parseUser(legacyUser);
    return cachedUser;
  }

  try {
    const storedUser = await SecureStorage.getItem(AUTH_USER_KEY);
    const serializedUser = typeof storedUser === 'string' ? storedUser : legacyUser;
    if (!storedUser && legacyUser) {
      await SecureStorage.setItem(AUTH_USER_KEY, legacyUser);
    }
    cachedUser = parseUser(serializedUser);
    return cachedUser;
  } finally {
    localStorage.removeItem(AUTH_USER_KEY);
  }
}

export async function setStoredAuthUser(user: User | null): Promise<void> {
  cachedUser = user;
  if (useSecureStorage) {
    try {
      if (user) await SecureStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
      else await SecureStorage.removeItem(AUTH_USER_KEY);
    } finally {
      localStorage.removeItem(AUTH_USER_KEY);
    }
    return;
  }
  if (user) localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
  else localStorage.removeItem(AUTH_USER_KEY);
}
