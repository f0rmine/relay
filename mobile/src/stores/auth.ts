import { defineStore } from 'pinia';
import { ApiError, apiFetch } from '@/api/client';
import type { TokenResponse, User } from '@/api/types';
import { apiUrl } from '@/config/env';
import { useConversationsStore } from '@/stores/conversations';
import { useMessagesStore } from '@/stores/messages';
import { useSocketStore } from '@/stores/socket';
import { initPushNotifications, unregisterPushNotifications } from '@/services/push';
import {
  clearAuthTokens,
  getAuthTokens,
  getStoredAuthUser,
  setAuthTokens,
  setStoredAuthUser
} from '@/services/auth-storage';

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  loading: boolean;
  restored: boolean;
  tokenListenerReady: boolean;
}

let restorePromise: Promise<void> | null = null;

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    user: null,
    accessToken: null,
    refreshToken: null,
    loading: false,
    restored: false,
    tokenListenerReady: false
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.accessToken)
  },
  actions: {
    async persist(tokens: TokenResponse) {
      try {
        await Promise.all([
          setAuthTokens(tokens.access_token, tokens.refresh_token),
          setStoredAuthUser(tokens.user)
        ]);
      } catch (error) {
        await Promise.allSettled([clearAuthTokens(), setStoredAuthUser(null)]);
        throw error;
      }
      this.accessToken = tokens.access_token;
      this.refreshToken = tokens.refresh_token;
      this.user = tokens.user;
      this.restored = true;
    },
    async setUser(user: User | null) {
      this.user = user;
      await setStoredAuthUser(user);
    },
    async syncFromStorage() {
      const [tokens, storedUser] = await Promise.all([getAuthTokens(), getStoredAuthUser()]);
      this.accessToken = tokens.accessToken;
      this.refreshToken = tokens.refreshToken;
      this.user = storedUser;
    },
    listenForTokenRefresh() {
      if (this.tokenListenerReady) return;
      this.tokenListenerReady = true;
      window.addEventListener('relay:tokens-refreshed', (event) => {
        const detail = (event as CustomEvent<TokenResponse>).detail;
        if (!detail?.access_token || !detail?.refresh_token) return;
        this.accessToken = detail.access_token;
        this.refreshToken = detail.refresh_token;
        this.user = detail.user;
      });
      window.addEventListener('relay:auth-expired', () => {
        useSocketStore().disconnect();
        void this.clear().catch(() => undefined);
      });
    },
    async restore() {
      this.listenForTokenRefresh();
      if (this.restored) return;
      if (restorePromise) return restorePromise;
      restorePromise = (async () => {
        try {
          await this.syncFromStorage();
          if (!this.accessToken) return;
          await this.setUser(await apiFetch<User>('/auth/me'));
          void useSocketStore().connect();
          void initPushNotifications();
        } catch (error) {
          if (error instanceof ApiError && error.status === 401) {
            await this.clear();
          }
        } finally {
          this.restored = true;
        }
      })().finally(() => {
        restorePromise = null;
      });
      return restorePromise;
    },
    async login(login: string, password: string) {
      this.loading = true;
      try {
        const response = await apiFetch<TokenResponse>('/auth/login', {
          method: 'POST',
          body: JSON.stringify({ login, password })
        });
        await this.persist(response);
        void useSocketStore().connect();
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
        await this.persist(response);
        void useSocketStore().connect();
        void initPushNotifications();
      } finally {
        this.loading = false;
      }
    },
    async refresh(): Promise<boolean> {
      if (!this.refreshToken) return false;
      try {
        const response = await fetch(apiUrl('/auth/refresh'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: this.refreshToken })
        });
        if (!response.ok) return false;
        await this.persist(await response.json());
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
      await this.clear();
    },
    async clear() {
      this.user = null;
      this.accessToken = null;
      this.refreshToken = null;
      this.restored = true;
      await Promise.all([clearAuthTokens(), setStoredAuthUser(null)]);
      useConversationsStore().reset();
      useMessagesStore().reset();
    }
  }
});
