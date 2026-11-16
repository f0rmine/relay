import * as Sentry from '@sentry/vue';

/**
 * Record a failure that is deliberately recovered from (best-effort work such
 * as push registration, refetches or media downloads) so it stays observable.
 *
 * Only the error object and a static context label are reported — never
 * message text, tokens or other user content. Expected conditions (offline,
 * expired auth) are skipped to keep the signal clean.
 */
export function reportError(context: string, error: unknown): void {
  if (isExpected(error)) return;
  if (import.meta.env.DEV) {
    console.warn(`[relay] ${context}`, error);
  }
  if (Sentry.getClient()) {
    Sentry.captureException(error, { tags: { context } });
  }
}

function isExpected(error: unknown): boolean {
  if (error instanceof DOMException && error.name === 'AbortError') return true;
  const status = (error as { status?: unknown } | null)?.status;
  // 0 = network unreachable, 401 = session expired (handled by auth flow).
  return status === 0 || status === 401;
}
