import { describe, expect, it, vi } from 'vitest';
import { createDetailView, renderDetail } from '../src/views/detailView.js';
import { createFilterBar } from '../src/views/filterBar.js';
import { MAP_CONFIG, buildMarkers, createMapView } from '../src/views/mapView.js';
import { createGeo } from '../src/geo.js';
import { sampleEvent } from './helpers.js';

describe('mapView.buildMarkers', () => {
  it('keeps only events with valid coordinates', () => {
    const ms = buildMarkers([sampleEvent(), sampleEvent({ uri: 'x', location: { name: 'No pin' } })], { timeZone: 'UTC', locale: 'en-US' });
    expect(ms).toEqual([{ uri: sampleEvent().uri, lat: 32.8797, lng: -117.2362, title: 'Taco Tuesday', subtitle: '7:00 PM – 9:00 PM · Price Center' }]);
  });

  it('tile provider is configurable', async () => {
    const L = fakeLeaflet();
    globalThis.L = L;
    const root = document.createElement('div');
    const view = createMapView(root, { config: { tileUrl: 'https://tiles.example/{z}/{x}/{y}.pbf' }, load: async () => L });
    await view.show([sampleEvent()]);
    expect(L.tileLayer).toHaveBeenCalledWith('https://tiles.example/{z}/{x}/{y}.pbf', expect.objectContaining({ maxZoom: MAP_CONFIG.maxZoom }));
    expect(L.marker).toHaveBeenCalledTimes(1);
    delete globalThis.L;
  });

  it('shows an error when Leaflet fails to load', async () => {
    const root = document.createElement('div');
    await createMapView(root, { load: async () => { throw new Error('x'); } }).show([]);
    expect(root.querySelector('[role=alert]')).not.toBeNull();
  });
});

function fakeLeaflet() {
  const chain = () => ({ addTo() { return this; }, bindPopup() { return this; }, setView() { return this; }, clearLayers() {}, invalidateSize() {}, fitBounds() {} });
  return { map: vi.fn(chain), tileLayer: vi.fn(chain), layerGroup: vi.fn(chain), marker: vi.fn(chain) };
}

describe('detailView', () => {
  it('renders description and updates newest first, escaped', () => {
    const ev = sampleEvent({ description: '<b>Bring</b> a plate', updates: [
      { text: 'Moved inside', sourceUri: null, createdAt: '2026-11-11T18:00:00Z' },
      { text: 'Starting soon!', sourceUri: null, createdAt: '2026-11-11T18:30:00Z' },
    ] });
    const root = document.createElement('div');
    root.append(...renderDetail(ev).filter(Boolean));
    expect(root.querySelector('.detail__desc').textContent).toBe('<b>Bring</b> a plate');
    expect(root.querySelector('b')).toBeNull();
    expect([...root.querySelectorAll('.updates p')].map((p) => p.textContent)).toEqual(['Starting soon!', 'Moved inside']);
    expect(root.textContent).not.toContain('Edit');
  });

  it('only links http(s) source URLs and shows edit controls for owners', () => {
    const root = document.createElement('div');
    root.append(...renderDetail(sampleEvent({ sourceUrl: 'javascript:alert(1)' }), { canEdit: true }).filter(Boolean));
    expect(root.querySelector('a[href^="javascript"]')).toBeNull();
    expect(root.textContent).toContain('Edit');
  });

  it('loads via api.getEvent and handles 404', async () => {
    const api = { getEvent: vi.fn(async () => { throw Object.assign(new Error('nf'), { status: 404 }); }) };
    const v = createDetailView({ api });
    await v.open('at://x');
    expect(api.getEvent).toHaveBeenCalledWith('at://x');
    expect(v.element.textContent).toContain('no longer available');
  });
});

describe('filterBar', () => {
  it('renders tags/groups and emits changes; search is debounced', async () => {
    vi.useFakeTimers();
    const onChange = vi.fn();
    const root = document.createElement('div');
    document.body.replaceChildren(root);
    const bar = createFilterBar(root, { onChange, debounceMs: 300 });
    bar.render({ tags: ['food'], group: '', q: '', nearMe: false }, { tags: [{ value: 'food', count: 2 }, { value: 'music', count: 1 }], groups: [{ value: 'ACM', count: 4 }] });
    const chips = root.querySelectorAll('.chip');
    expect(chips[0].getAttribute('aria-pressed')).toBe('true');
    chips[1].click();
    expect(onChange).toHaveBeenLastCalledWith({ tags: ['food', 'music'] });
    const select = root.querySelector('select');
    expect([...select.options].map((o) => o.textContent)).toEqual(['All groups', 'ACM (4)']);
    select.value = 'ACM';
    select.dispatchEvent(new Event('change'));
    expect(onChange).toHaveBeenLastCalledWith({ group: 'ACM' });
    const input = root.querySelector('input[type=search]');
    input.value = 'ta'; input.dispatchEvent(new Event('input'));
    input.value = 'tacos'; input.dispatchEvent(new Event('input'));
    expect(onChange).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(300);
    expect(onChange).toHaveBeenLastCalledWith({ q: 'tacos' });
    root.querySelector('button.btn').click();
    expect(onChange).toHaveBeenLastCalledWith({ nearMe: true });
    vi.useRealTimers();
  });
});

describe('geo', () => {
  it('keeps the position in memory only and can clear it', async () => {
    const geolocation = { getCurrentPosition: (ok) => ok({ coords: { latitude: 32.88, longitude: -117.23 } }) };
    const g = createGeo({ geolocation });
    expect(g.position).toBeNull();
    expect(await g.request()).toEqual({ lat: 32.88, lng: -117.23 });
    expect(g.position).toEqual({ lat: 32.88, lng: -117.23 });
    g.clear();
    expect(g.position).toBeNull();
    await expect(createGeo({ geolocation: null }).request()).rejects.toThrow();
  });
});
