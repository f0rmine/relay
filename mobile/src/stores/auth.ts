import { defineStore } from 'pinia';
import { apiFetch } from '@/api/client';
import type { TokenResponse, User } from '@/api/types';
import { API_BASE_URL } from '@/config/env';
import { useSocketStore } from '@/stores/socket';
import { initPushNotifications, unregisterPushNotifications } from '@/services/push';

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  loading: boolean;
  restored: boolean;
  tokenListenerReady: boolean;
}

function storedUser(): User | null {
  const raw = localStorage.getItem('authUser');
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    localStorage.removeItem('authUser');
    return null;
  }
}

let restorePromise: Promise<void> | null = null;

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    user: storedUser(),
    accessToken: localStorage.getItem('accessToken'),
    refreshToken: localStorage.getItem('refreshToken'),
    loading: false,
    restored: false,
    tokenListenerReady: false
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.accessToken)
  },
  actions: {
    persist(tokens: TokenResponse) {
      this.accessToken = tokens.access_token;
      this.refreshToken = tokens.refresh_token;
      this.restored = true;
      this.setUser(tokens.user);
      localStorage.setItem('accessToken', tokens.access_token);
      localStorage.setItem('refreshToken', tokens.refresh_token);
    },
    setUser(user: User | null) {
      this.user = user;
      if (user) localStorage.setItem('authUser', JSON.stringify(user));
      else localStorage.removeItem('authUser');
    },
    syncFromStorage() {
      this.accessToken = localStorage.getItem('accessToken');
      this.refreshToken = localStorage.getItem('refreshToken');
      this.user = storedUser();
    },
    listenForTokenRefresh() {
      if (this.tokenListenerReady) return;
      this.tokenListenerReady = true;
      window.addEventListener('relay:tokens-refreshed', (event) => {
        const detail = (event as CustomEvent<TokenResponse>).detail;
        if (!detail?.access_token || !detail?.refresh_token) return;
        this.accessToken = detail.access_token;
        this.refreshToken = detail.refresh_token;
        this.setUser(detail.user);
      });
      window.addEventListener('relay:auth-expired', () => {
        useSocketStore().disconnect();
        this.clear();
      });
    },
    async restore() {
      this.listenForTokenRefresh();
      if (this.restored) return;
      if (restorePromise) return restorePromise;
      this.syncFromStorage();
      if (!this.accessToken) {
        this.restored = true;
        return;
      }
      restorePromise = (async () => {
        try {
          this.setUser(await apiFetch<User>('/auth/me'));
          useSocketStore().connect();
          void initPushNotifications();
        } catch {
          this.clear();
        } finally {
          this.restored = true;
          restorePromise = null;
        }
      })();
      return restorePromise;
    },
    async login(login: string, password: string) {
      this.loading = true;
      try {
        const response = await apiFetch<TokenResponse>('/auth/login', {
          method: 'POST',
          body: JSON.stringify({ login, password })
        });
        this.persist(response);
        useSocketStore().connect();
        void initPushNotifications();
      } finally {
        this.loading = false;
      }
    },
    async register(username: string, display_name: string, email: string, password: string) {
      this.loading = true;
      try {
        const response = await apiFetch<TokenResponse>('/auth/register', {
          method: 'POST',
          body: JSON.stringify({ username, display_name, email, password })
        });
        this.persist(response);
        useSocketStore().connect();
        void initPushNotifications();
      } finally {
        this.loading = false;
      }
    },
    async refresh(): Promise<boolean> {
      if (!this.refreshToken) return false;
      try {
        const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: this.refreshToken })
        });
        if (!response.ok) return false;
        this.persist(await response.json());
        return true;
      } catch {
        return false;
      }
    },
    async logout() {
      try {
        await apiFetch<void>('/auth/logout', {
          method: 'POST',
          body: JSON.stringify({ refresh_token: this.refreshToken })
        });
      } catch {
        // Local logout still succeeds if the backend is unreachable.
      }
      await unregisterPushNotifications();
      useSocketStore().disconnect();
      this.clear();
    },
    clear() {
      this.setUser(null);
      this.accessToken = null;
      this.refreshToken = null;
      this.restored = true;
      localStorage.removeItem('accessToken');
      localStorage.removeItem('refreshToken');
    }
  }
});
