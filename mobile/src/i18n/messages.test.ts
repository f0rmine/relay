import { describe, expect, it } from 'vitest';
import { messages } from './messages';

function keys(value: object, prefix = ''): string[] {
  return Object.entries(value).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return child && typeof child === 'object' ? keys(child, path) : [path];
  });
}

describe('translation dictionaries', () => {
  it('contains only English and Ukrainian locales', () => {
    expect(Object.keys(messages).sort()).toEqual(['en', 'uk']);
  });

  it('keeps both locale key sets in sync', () => {
    expect(keys(messages.uk).sort()).toEqual(keys(messages.en).sort());
  });
});
