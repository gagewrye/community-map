import { describe, expect, it, vi } from 'vitest';
import { h, safeHttpUrl } from '../src/dom.js';

describe('h()', () => {
  it('escapes text children and sets attributes/handlers', () => {
    const fn = vi.fn();
    const el = h('button', { class: 'b', 'aria-pressed': 'true', onclick: fn, dataset: { k: 'v' } }, '<img src=x onerror=alert(1)>', null, ['a', 1]);
    expect(el.querySelector('img')).toBeNull();
    expect(el.textContent).toBe('<img src=x onerror=alert(1)>a1');
    expect(el.className).toBe('b');
    expect(el.dataset.k).toBe('v');
    el.click();
    expect(fn).toHaveBeenCalled();
  });

  it('safeHttpUrl allows only http(s)', () => {
    expect(safeHttpUrl('https://ucsd.edu/x')).toBe('https://ucsd.edu/x');
    expect(safeHttpUrl('javascript:alert(1)')).toBeNull();
    expect(safeHttpUrl(null)).toBeNull();
  });
});
