import { describe, expect, it, vi } from 'vitest';
import { createStore } from '../src/store.js';

describe('store', () => {
  it('merges patches and notifies with prev state', () => {
    const s = createStore({ a: 1, b: 2 });
    const fn = vi.fn();
    s.subscribe(fn);
    s.set({ a: 3 });
    expect(s.get()).toEqual({ a: 3, b: 2 });
    expect(fn).toHaveBeenCalledWith({ a: 3, b: 2 }, { a: 1, b: 2 });
  });

  it('supports functional updates and unsubscribe', () => {
    const s = createStore({ n: 1 });
    const fn = vi.fn();
    const off = s.subscribe(fn);
    s.set((st) => ({ n: st.n + 1 }));
    off();
    s.set({ n: 10 });
    expect(fn).toHaveBeenCalledTimes(1);
    expect(s.get().n).toBe(10);
  });

  it('does not mutate the initial object', () => {
    const init = { n: 1 };
    createStore(init).set({ n: 2 });
    expect(init.n).toBe(1);
  });
});
