import { describe, expect, it } from 'vitest';
import { createCache } from '../src/cache.js';
import { memoryStorage } from './helpers.js';

describe('cache', () => {
  it('round-trips values with savedAt', () => {
    const c = createCache({ storage: memoryStorage(), now: () => 42 });
    c.set('a', { x: 1 });
    expect(c.get('a')).toEqual({ value: { x: 1 }, savedAt: 42 });
    c.remove('a');
    expect(c.get('a')).toBeNull();
  });

  it('never throws when storage throws', () => {
    const bad = { getItem() { throw new Error('denied'); }, setItem() { throw new Error('quota'); }, removeItem() { throw new Error('x'); }, get length() { throw new Error('x'); } };
    const c = createCache({ storage: bad });
    expect(c.set('a', 1)).toBe(false);
    expect(c.get('a')).toBeNull();
    expect(() => c.clear()).not.toThrow();
  });

  it('works with null storage and ignores corrupt entries', () => {
    expect(createCache({ storage: null }).get('a')).toBeNull();
    const s = memoryStorage();
    s.setItem('cm:cache:a', '{not json');
    expect(createCache({ storage: s }).get('a')).toBeNull();
  });

  it('clears only its own prefix', () => {
    const s = memoryStorage();
    s.setItem('other', '1');
    const c = createCache({ storage: s });
    c.set('a', 1);
    c.clear();
    expect(s.getItem('other')).toBe('1');
    expect(c.get('a')).toBeNull();
  });
});
