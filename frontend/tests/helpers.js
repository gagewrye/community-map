/** Test helpers. */

/** In-memory Storage implementation. */
export function memoryStorage() {
  const m = new Map();
  return {
    get length() { return m.size; },
    key: (i) => [...m.keys()][i] ?? null,
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k),
    clear: () => m.clear(),
  };
}

/** Minimal fetch Response stand-in. */
export function jsonResponse(body, status = 200, headers = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (k) => headers[k.toLowerCase()] ?? null },
    text: async () => (body === undefined ? '' : JSON.stringify(body)),
  };
}

/** Sample EventView. */
export function sampleEvent(over = {}) {
  return {
    uri: 'at://did:plc:abc/app.communitymap.event/3kabc',
    cid: 'bafy1', authorDid: 'did:plc:abc', authorHandle: 'alice.test', source: 'atproto',
    name: 'Taco Tuesday', description: 'Free tacos', startsAt: '2026-11-11T19:00:00Z', endsAt: '2026-11-11T21:00:00Z',
    location: { name: 'Price Center', address: '9500 Gilman Dr', lat: '32.8797', lng: '-117.2362' },
    tags: ['food', 'free'], group: 'Triton Eats', sourceUrl: null,
    indexedAt: '2026-11-10T00:00:00Z', updatedAt: '2026-11-10T00:00:00Z', status: 'upcoming',
    ...over,
  };
}
