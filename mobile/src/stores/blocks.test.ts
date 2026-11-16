import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ apiFetch: vi.fn(), reportError: vi.fn() }));
vi.mock('@/api/client', () => ({ apiFetch: mocks.apiFetch }));
vi.mock('@/services/errors', () => ({ reportError: mocks.reportError }));

import { useBlocksStore } from './blocks';

const user = (id: string) => ({ id, username: id, display_name: id }) as never;

describe('blocks store', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    mocks.apiFetch.mockReset();
    mocks.reportError.mockReset();
  });

  it('refetches the authoritative list after blocking', async () => {
    mocks.apiFetch.mockResolvedValueOnce(undefined).mockResolvedValueOnce([user('u1')]);
    const store = useBlocksStore();
    await store.block('u1');
    expect(mocks.apiFetch).toHaveBeenNthCalledWith(1, '/users/u1/block', { method: 'POST' });
    expect(store.blocked.map((u) => u.id)).toEqual(['u1']);
  });

  it('keeps the previous list and reports when the refetch fails', async () => {
    const store = useBlocksStore();
    store.blocked = [user('u0')];
    const failure = new Error('refetch failed');
    mocks.apiFetch.mockResolvedValueOnce(undefined).mockRejectedValueOnce(failure);
    await expect(store.block('u1')).resolves.toBeUndefined();
    expect(store.blocked.map((u) => u.id)).toEqual(['u0']);
    expect(mocks.reportError).toHaveBeenCalledWith('blocks.refetch', failure);
  });

  it('propagates a failed block request', async () => {
    mocks.apiFetch.mockRejectedValueOnce(new Error('forbidden'));
    await expect(useBlocksStore().block('u1')).rejects.toThrow('forbidden');
  });

  it('removes the user locally on unblock', async () => {
    mocks.apiFetch.mockResolvedValueOnce(undefined);
    const store = useBlocksStore();
    store.blocked = [user('u1'), user('u2')];
    await store.unblock('u1');
    expect(store.blocked.map((u) => u.id)).toEqual(['u2']);
  });
});
