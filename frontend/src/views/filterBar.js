/**
 * Filter bar: debounced text search, group select, tag chips, "Near me" toggle.
 * Stateless UI: it renders a FilterState and reports changes via onChange(patch).
 * @module views/filterBar
 */
import { h } from '../dom.js';
import { toggleTag } from '../filters.js';
import { debounce } from '../util.js';

/**
 * @param {HTMLElement} root
 * @param {{onChange: (patch: Partial<import('../filters.js').FilterState>) => void,
 *   debounceMs?: number, geoSupported?: boolean}} opts
 * @returns {{render(state: import('../filters.js').FilterState,
 *   options: {tags: {value: string, count: number}[], groups: {value: string, count: number}[],
 *   nearMeBusy?: boolean}): void}}
 */
export function createFilterBar(root, { onChange, debounceMs = 300, geoSupported = true }) {
  let state = { tags: [], group: '', q: '', nearMe: false };
  const emitQ = debounce((q) => onChange({ q }), debounceMs);

  const search = h('input', {
    type: 'search', id: 'f-q', name: 'q', autocomplete: 'off', placeholder: 'Search events',
    oninput: (e) => emitQ(e.target.value),
  });
  const group = h('select', { id: 'f-group', name: 'group', onchange: (e) => onChange({ group: e.target.value }) });
  const nearMe = h('button', {
    type: 'button', class: 'btn', 'aria-pressed': 'false', hidden: !geoSupported,
    onclick: () => onChange({ nearMe: !state.nearMe }),
  }, 'Near me');
  const chips = h('ul', { class: 'chips', 'aria-label': 'Filter by tag' });

  root.replaceChildren(
    h('div', { class: 'filters__row' },
      h('label', { for: 'f-q', class: 'visually-hidden' }, 'Search events'), search,
      h('label', { for: 'f-group', class: 'visually-hidden' }, 'Group'), group,
      nearMe,
    ),
    chips,
  );

  function render(next, { tags = [], groups = [], nearMeBusy = false } = {}) {
    state = next;
    if (document.activeElement !== search && search.value !== next.q) search.value = next.q;
    renderGroups(groups, next.group);
    nearMe.setAttribute('aria-pressed', String(next.nearMe));
    nearMe.textContent = nearMeBusy ? 'Locating…' : 'Near me';
    renderChips(tags, next.tags);
  }

  function renderGroups(groups, selected) {
    const opts = [h('option', { value: '' }, 'All groups'),
      ...groups.map((g) => h('option', { value: g.value }, `${g.value} (${g.count})`))];
    if (selected && !groups.some((g) => g.value === selected)) opts.push(h('option', { value: selected }, selected));
    group.replaceChildren(...opts);
    group.value = selected || '';
  }

  function renderChips(tags, active) {
    const focused = document.activeElement?.dataset?.tag;
    const values = [...new Set([...active, ...tags.map((t) => t.value)])];
    chips.replaceChildren(...values.map((v) => h('li', null,
      h('button', {
        type: 'button', class: 'chip', 'aria-pressed': String(active.includes(v)), dataset: { tag: v },
        onclick: () => onChange({ tags: toggleTag(state.tags, v) }),
      }, `#${v}`),
    )));
    if (focused) [...chips.querySelectorAll('button')].find((b) => b.dataset.tag === focused)?.focus();
  }

  return { render };
}
