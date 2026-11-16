import type { BrowserOptions } from '@sentry/vue';

/**
 * Privacy-first Sentry options. Since Sentry v11, every `dataCollection`
 * category defaults to ON (headers, cookies, bodies, query params, user info,
 * local variables), so each one is disabled explicitly here. Error reports
 * carry stack traces, release info and our static `context` tags only.
 */
export function sentryPrivacyOptions(): Pick<BrowserOptions, 'dataCollection' | 'tracesSampleRate'> {
  return {
    tracesSampleRate: 0.1,
    dataCollection: {
      userInfo: false,
      cookies: false,
      httpHeaders: { request: false, response: false },
      httpBodies: [],
      urlQueryParams: false,
      graphQL: { document: false, variables: false },
      genAI: { inputs: false, outputs: false },
      mcp: { inputs: false, outputs: false },
      databaseQueryData: false,
      queues: false,
      stackFrameVariables: false
    }
  };
}
