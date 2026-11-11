/**
 * Small localStorage-backed response cache. Every storage access is guarded.
 * @module cache
 */
import { getStorage, storageGet, storageSet } from './util.js';

/**
 * @typedef {{value: any, savedAt: number}} CacheEntry
 * @typedef {{get(key: string): CacheEntry|null, set(key: string, value: any): boolean,
 *            remove(key: string): void, clear(): void}} Cache
 */

/**
 * Create a cache.
 * @param {{storage?: Storage|null, prefix?: string, now?: () => number}} [opts]
 * @returns {Cache}
 */
export function createCache({ storage = getStorage('localStorage'), prefix = 'cm:cache:', now = Date.now } = {}) {
  const keyOf = (k) => prefix + k;

  function get(key) {
    const raw = storageGet(storage, keyOf(key));
    if (!raw) return null;
    try {
      const entry = JSON.parse(raw);
      return entry && 'value' in entry ? entry : null;
    } catch {
      return null;
    }
  }

  function set(key, value) {
    const raw = JSON.stringify({ value, savedAt: now() });
    if (storageSet(storage, keyOf(key), raw)) return true;
    clear(); // probably quota: drop our old entries and retry once
    return storageSet(storage, keyOf(key), raw);
  }

  function remove(key) {
    storageSet(storage, keyOf(key), null);
  }

  function clear() {
    try {
      for (let i = storage.length - 1; i >= 0; i--) {
        const k = storage.key(i);
        if (k && k.startsWith(prefix)) storage.removeItem(k);
      }
    } catch {
      /* storage unavailable */
    }
  }

  return { get, set, remove, clear };
}
