import { defineStore } from 'pinia';
import { apiFetch } from '@/api/client';
import type { User } from '@/api/types';
import { reportError } from '@/services/errors';

interface BlockState {
  blocked: User[];
}

export const useBlocksStore = defineStore('blocks', {
  state: (): BlockState => ({
    blocked: []
  }),
  actions: {
    reset() {
      this.blocked = [];
    },
    async fetchBlocked(): Promise<User[]> {
      this.blocked = await apiFetch<User[]>('/users/me/blocked');
      return this.blocked;
    },
    async block(userId: string): Promise<void> {
      await apiFetch(`/users/${userId}/block`, { method: 'POST' });
      // Keep local list in sync via authoritative refetch; a failed
      // refetch must not mask the successful block.
      try {
        await this.fetchBlocked();
      } catch (error) {
        // Keep the previous list; next fetch will resync.
        reportError('blocks.refetch', error);
      }
    },
    async unblock(userId: string): Promise<void> {
      await apiFetch(`/users/${userId}/block`, { method: 'DELETE' });
      this.blocked = this.blocked.filter((user) => user.id !== userId);
    }
  }
});
