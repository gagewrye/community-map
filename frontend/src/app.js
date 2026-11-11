/**
 * Application entry: wires store, API, views, writers and subscriptions together.
 * @module app
 */
import { createApi } from './api.js';
import { createAtprotoWriter } from './atproto.js';
import { createDevWriter } from './devWriter.js';
import { h } from './dom.js';
import { EMPTY_FILTERS, buildEventQuery, sortByDistance, toggleTag } from './filters.js';
import { createGeo } from './geo.js';
import { createStore } from './store.js';
import { createSubscriptions } from './subscriptions.js';
import { createToaster } from './toast.js';
import { createComposeView } from './views/composeView.js';
import { createDetailView } from './views/detailView.js';
import { createFilterBar } from './views/filterBar.js';
import { createListView } from './views/listView.js';
import { createLoginView } from './views/loginView.js';
import { createMapView } from './views/mapView.js';

const $ = (sel) => document.querySelector(sel);

/**
 * Start the app. API base comes from <meta name="cm-api-base"> (default: same origin).
 * @param {{baseUrl?: string}} [opts]
 */
export async function start({ baseUrl = $('meta[name="cm-api-base"]')?.content ?? '' } = {}) {
  const api = createApi({ baseUrl });
  const toast = createToaster($('#toasts'));
  const geo = createGeo();
  const atproto = createAtprotoWriter();
  let devWriter = null;
  const store = createStore({
    config: null, filters: { ...EMPTY_FILTERS }, events: [], cursor: null, loading: false,
    stale: false, savedAt: null, error: null, tags: [], groups: [], subscribed: new Set(),
    locating: false, tab: 'list',
  });

  const writer = () => (atproto.loggedIn ? atproto : devWriter);
  const canEdit = (ev) => Boolean(writer()) && ev.authorDid === writer().did && ev.source !== 'ical';

  // --- data loading ---
  let seq = 0;
  async function loadEvents({ append = false } = {}) {
    const mine = ++seq;
    const { filters, cursor, events } = store.get();
    store.set({ loading: true, error: null });
    try {
      const { data, stale, savedAt } = await api.listEvents(buildEventQuery(filters, { cursor: append ? cursor : null }));
      if (mine !== seq) return;
      const merged = append ? dedupe([...events, ...data.events]) : data.events;
      store.set({ events: merged, cursor: data.cursor ?? null, stale, savedAt: savedAt ?? null, loading: false });
    } catch (err) {
      if (mine !== seq) return;
      store.set({ loading: false, error: err.offline ? "You're offline and no saved events are available yet." : 'Could not load events. Please try again.' });
    }
  }

  async function loadFacets() {
    const [tags, groups] = await Promise.allSettled([api.tags(), api.groups()]);
    store.set({
      tags: tags.status === 'fulfilled' ? tags.value.data : [],
      groups: groups.status === 'fulfilled' ? groups.value.data : [],
    });
  }

  // --- filters ---
  async function changeFilters(patch) {
    const filters = { ...store.get().filters, ...patch };
    if (patch.nearMe && !geo.position) {
      store.set({ locating: true });
      try {
        await geo.request();
      } catch (err) {
        toast(err.message, { kind: 'error' });
        filters.nearMe = false;
      }
      store.set({ locating: false });
    }
    if (!filters.nearMe) geo.clear();
    store.set({ filters });
    const refetch = ['tags', 'group', 'q'].some((k) => k in patch);
    if (refetch) loadEvents();
  }

  const visibleEvents = () => {
    const { events, filters } = store.get();
    return filters.nearMe && geo.position ? sortByDistance(events, geo.position) : events;
  };

  // --- views ---
  const subs = createSubscriptions({
    api, toast,
    onChange: (subscribed) => store.set({ subscribed }),
    onNotification: (n) => applyNotification(n),
  });
  const detail = createDetailView({ api, canEdit, onEdit: (ev) => compose.open(ev), onDelete: (ev) => compose.remove(ev) });
  const compose = createComposeView({
    getWriter: writer, geo, toast,
    onSaved: () => { toast('Event saved. It can take a few seconds to appear.'); setTimeout(() => { loadEvents(); loadFacets(); }, 1500); },
    onDeleted: (uri) => { toast('Event deleted.'); store.set({ events: store.get().events.filter((e) => e.uri !== uri) }); },
  });
  const login = createLoginView({ login: (id, pw) => atproto.login(id, pw), onLoggedIn: renderAccount });
  const filterBar = createFilterBar($('#filters'), { onChange: changeFilters, geoSupported: geo.supported });
  const list = createListView($('#list'), { onLoadMore: () => loadEvents({ append: true }) });
  const map = createMapView($('#map'), { onOpen: (uri) => detail.open(uri) });

  async function toggleSubscribe(uri) {
    try {
      await subs.toggle(uri);
    } catch {
      toast('Could not update subscription — check your connection.', { kind: 'error' });
    }
  }

  async function applyNotification(n) {
    const { events } = store.get();
    if (n.kind === 'deleted' || n.kind === 'expired') {
      store.set({ events: events.filter((e) => e.uri !== n.eventUri) });
    } else if (n.kind === 'updated' && events.some((e) => e.uri === n.eventUri)) {
      try {
        const { data } = await api.getEvent(n.eventUri);
        store.set({ events: store.get().events.map((e) => (e.uri === data.uri ? data : e)) });
      } catch { /* keep old copy */ }
    }
  }

  function render() {
    const s = store.get();
    filterBar.render(s.filters, { tags: s.tags, groups: s.groups, nearMeBusy: s.locating });
    const shown = visibleEvents();
    list.render({
      events: shown, hasMore: Boolean(s.cursor), loading: s.loading, stale: s.stale, savedAt: s.savedAt,
      error: s.error, activeTags: s.filters.tags, subscribed: s.subscribed,
      onOpen: (uri) => detail.open(uri),
      onTagClick: (tag) => changeFilters({ tags: toggleTag(store.get().filters.tags, tag) }),
      onToggleSubscribe: toggleSubscribe,
    });
    if (s.tab === 'map') map.show(shown);
  }

  function renderAccount() {
    const root = $('#account');
    const canPost = Boolean(writer());
    const items = [];
    if (atproto.loggedIn) {
      items.push(h('span', { class: 'muted' }, `@${atproto.handle}`),
        h('button', { type: 'button', class: 'btn', onclick: async () => { await atproto.logout(); renderAccount(); } }, 'Log out'));
    } else {
      if (devWriter) items.push(h('span', { class: 'badge', title: 'Posts go to the local dev index only' }, 'Demo mode'));
      items.push(h('button', { type: 'button', class: 'btn', onclick: () => login.open() }, 'Log in'));
    }
    if (canPost) items.push(h('button', { type: 'button', class: 'btn btn--primary', onclick: () => compose.open() }, 'New event'));
    root.replaceChildren(...items);
    render(); // edit rights may have changed
  }

  setupTabs(store);
  store.subscribe((s, prev) => {
    if (s.tab !== prev.tab) showTab(s.tab);
    render();
  });
  window.addEventListener('online', () => {
    if (store.get().stale || store.get().error) loadEvents();
    subs.reconnectNow();
  });

  try {
    const { data } = await api.config();
    store.set({ config: data });
    if (data?.devMode) devWriter = createDevWriter({ api });
  } catch { /* offline with nothing cached: read-only */ }
  renderAccount();
  loadFacets();
  loadEvents();
  subs.load();
  registerServiceWorker();
}

function dedupe(events) {
  const seen = new Set();
  return events.filter((e) => !seen.has(e.uri) && seen.add(e.uri));
}

function setupTabs(store) {
  const tabs = [...document.querySelectorAll('[role=tab]')];
  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => store.set({ tab: tab.dataset.tab }));
    tab.addEventListener('keydown', (e) => {
      const d = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
      if (!d) return;
      const next = tabs[(i + d + tabs.length) % tabs.length];
      next.focus();
      store.set({ tab: next.dataset.tab });
    });
  });
}

function showTab(name) {
  for (const tab of document.querySelectorAll('[role=tab]')) {
    const on = tab.dataset.tab === name;
    tab.setAttribute('aria-selected', String(on));
    tab.tabIndex = on ? 0 : -1;
    document.getElementById(tab.getAttribute('aria-controls')).hidden = !on;
  }
}

function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return;
  navigator.serviceWorker.register('./sw.js').catch(() => { /* offline support is best-effort */ });
}

if (typeof window !== 'undefined' && !globalThis.__CM_NO_AUTOSTART__ && document.querySelector('#list')) {
  start();
}
