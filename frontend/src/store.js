/**
 * Tiny observable state store — the app's entire "framework".
 * @module store
 */

/**
 * @template T
 * @typedef {{get(): T, set(patch: Partial<T> | ((s: T) => Partial<T>)): void,
 *            subscribe(fn: (state: T, prev: T) => void): () => void}} Store
 */

/**
 * Create a store holding a plain object. `set` shallow-merges and notifies subscribers.
 * @template {object} T
 * @param {T} initial
 * @returns {Store<T>}
 */
export function createStore(initial) {
  let state = { ...initial };
  const listeners = new Set();

  return {
    get: () => state,
    set(patch) {
      const prev = state;
      const delta = typeof patch === 'function' ? patch(prev) : patch;
      state = { ...prev, ...delta };
      for (const fn of [...listeners]) fn(state, prev);
    },
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };
}
