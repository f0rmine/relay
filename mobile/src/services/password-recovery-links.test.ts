import { describe, expect, it, vi } from 'vitest';
import { registerPasswordRecoveryLinks } from './password-recovery-links';

function harness(launchUrl?: string) {
  let listener: ((event: { url: string }) => void) | undefined;
  const app = {
    addListener: vi.fn(async (
      _eventName: 'appUrlOpen',
      callback: (event: { url: string }) => void
    ) => {
      listener = callback;
      return {};
    }),
    getLaunchUrl: vi.fn(async () => launchUrl ? { url: launchUrl } : undefined)
  };
  const router = {
    isReady: vi.fn(async () => undefined),
    replace: vi.fn()
  };
  registerPasswordRecoveryLinks(app, router);
  return { app, router, open: (url: string) => listener?.({ url }) };
}

describe('native password-recovery links', () => {
  it('routes a cold-start URL after the router is ready', async () => {
    const { app, router } = harness('relay://reset-password?token=cold-token');
    await vi.waitFor(() => expect(router.replace).toHaveBeenCalledWith({
      path: '/reset-password',
      query: { token: 'cold-token' }
    }));

    expect(app.getLaunchUrl).toHaveBeenCalledOnce();
    expect(router.isReady).toHaveBeenCalledOnce();
  });

  it('routes a live HTTPS App Link and ignores unrelated links', async () => {
    const { open, router } = harness();
    await Promise.resolve();
    expect(router.isReady).not.toHaveBeenCalled();

    open('https://relay.example.com/not-reset?token=secret');
    open('https://relay.example.com/reset-password?token=live-token');

    await vi.waitFor(() => expect(router.replace).toHaveBeenCalledWith({
      path: '/reset-password',
      query: { token: 'live-token' }
    }));
  });

  it('does not navigate twice when startup and live events contain the same token', async () => {
    const url = 'relay://reset-password?token=one-token';
    const { open, router } = harness(url);
    await vi.waitFor(() => expect(router.replace).toHaveBeenCalledOnce());

    open(url);
    await Promise.resolve();

    expect(router.replace).toHaveBeenCalledOnce();
  });

  it('allows the same link to be retried after navigation fails', async () => {
    const url = 'relay://reset-password?token=retry-token';
    const { open, router } = harness();
    router.isReady.mockRejectedValueOnce(new Error('router failed'));
    await Promise.resolve();

    open(url);
    await vi.waitFor(() => expect(router.isReady).toHaveBeenCalledOnce());
    await Promise.resolve();
    open(url);

    await vi.waitFor(() => expect(router.isReady).toHaveBeenCalledTimes(2));
  });
});
