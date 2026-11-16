import { beforeEach, describe, expect, it, vi } from 'vitest';

const sentry = vi.hoisted(() => ({
  getClient: vi.fn<() => object | undefined>(() => undefined),
  captureException: vi.fn()
}));
vi.mock('@sentry/vue', () => sentry);

import { reportError } from './errors';

describe('reportError', () => {
  beforeEach(() => {
    sentry.getClient.mockReset().mockReturnValue(undefined);
    sentry.captureException.mockReset();
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
  });

  it('does not touch Sentry when it is not initialized', () => {
    reportError('ctx', new Error('boom'));
    expect(sentry.captureException).not.toHaveBeenCalled();
  });

  it('captures with only a context tag when Sentry is active', () => {
    sentry.getClient.mockReturnValue({});
    const error = new Error('boom');
    reportError('push.register', error);
    expect(sentry.captureException).toHaveBeenCalledWith(error, { tags: { context: 'push.register' } });
  });

  it('skips expected offline, auth and abort failures', () => {
    sentry.getClient.mockReturnValue({});
    reportError('a', Object.assign(new Error('offline'), { status: 0 }));
    reportError('b', Object.assign(new Error('expired'), { status: 401 }));
    reportError('c', new DOMException('aborted', 'AbortError'));
    expect(sentry.captureException).not.toHaveBeenCalled();
  });

  it('still reports server errors', () => {
    sentry.getClient.mockReturnValue({});
    reportError('d', Object.assign(new Error('server'), { status: 500 }));
    expect(sentry.captureException).toHaveBeenCalledTimes(1);
  });
});
