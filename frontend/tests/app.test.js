import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { jsonResponse, memoryStorage, sampleEvent } from './helpers.js';

globalThis.__CM_NO_AUTOSTART__ = true;
const { start } = await import('../src/app.js');

const html = readFileSync(resolve(__dirname, '../index.html'), 'utf8');
const flush = () => new Promise((r) => setTimeout(r, 0));

function routes(url) {
  const path = url.split('?')[0];
  return {
    '/api/config': { devMode: true, jetstreamEnabled: false, eventNsid: 'app.communitymap.event', listenerNsid: 'app.communitymap.listener' },
    '/api/events': { events: [sampleEvent({ startsAt: new Date(Date.now() + 3600e3).toISOString(), endsAt: new Date(Date.now() + 7200e3).toISOString() })], cursor: null },
    '/api/tags': [{ value: 'food', count: 1 }],
    '/api/groups': [{ value: 'Triton Eats', count: 1 }],
    '/api/subscriptions': [],
  }[path];
}

describe('app (smoke)', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('boots in demo mode and renders events, tags and the New event button', async () => {
    document.documentElement.innerHTML = html.replace(/<script[^>]*><\/script>/, '');
    vi.stubGlobal('localStorage', memoryStorage());
    vi.stubGlobal('sessionStorage', memoryStorage());
    const f = vi.fn(async (url) => jsonResponse(routes(url) ?? { error: 'nf' }, routes(url) ? 200 : 404));
    vi.stubGlobal('fetch', f);
    await start();
    await flush(); await flush();
    expect(document.querySelectorAll('#list article')).toHaveLength(1);
    expect(document.querySelector('#filters .chip').textContent).toBe('#food');
    expect(document.querySelector('#account').textContent).toContain('Demo mode');
    expect(document.querySelector('#account').textContent).toContain('New event');
    // Location is never sent to the backend.
    expect(f.mock.calls.every(([u]) => !/lat|lng|near/i.test(u))).toBe(true);

    document.querySelector('#filters .chip').click();
    await flush();
    expect(f.mock.calls.some(([u]) => u.startsWith('/api/events?') && u.includes('tag=food'))).toBe(true);

    document.querySelector('#tab-map').click();
    expect(document.querySelector('#panel-map').hidden).toBe(false);
    expect(document.querySelector('#panel-list').hidden).toBe(true);
  });
});
