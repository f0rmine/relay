import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('web security policy', () => {
  it('restricts executable content and referrer data', () => {
    const html = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8');

    expect(html).toContain("script-src 'self'");
    expect(html).toContain("object-src 'none'");
    expect(html).toContain("base-uri 'self'");
    expect(html).toContain('name="referrer" content="no-referrer"');
    expect(html).not.toContain("script-src 'self' 'unsafe-inline'");
  });
});
