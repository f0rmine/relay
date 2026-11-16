import { describe, expect, it } from 'vitest';
import { sentryPrivacyOptions } from './sentry';

describe('sentryPrivacyOptions', () => {
  it('disables every data collection category', () => {
    const { dataCollection } = sentryPrivacyOptions();
    expect(dataCollection).toEqual({
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
    });
  });

  it('never enables a category that would carry tokens or message content', () => {
    const flat = JSON.stringify(sentryPrivacyOptions().dataCollection);
    expect(flat).not.toContain('true');
  });
});
