/**
 * Pure functions over filter state and event lists.
 * @module filters
 */

/**
 * @typedef {{tags: string[], group: string, q: string, nearMe: boolean}} FilterState
 */

/** @type {FilterState} */
export const EMPTY_FILTERS = Object.freeze({ tags: [], group: '', q: '', nearMe: false });

/**
 * Build GET /api/events params from filter state. `nearMe` is never sent (privacy).
 * @param {FilterState} filters
 * @param {{cursor?: string|null, limit?: number}} [page]
 * @returns {Record<string, any>}
 */
export function buildEventQuery(filters, { cursor = null, limit = 20 } = {}) {
  const params = { limit };
  if (filters.tags?.length) params.tag = [...filters.tags];
  if (filters.group) params.group = filters.group;
  const q = (filters.q || '').trim();
  if (q) params.q = q;
  if (cursor) params.cursor = cursor;
  return params;
}

/**
 * Toggle a tag in a tag list (returns a new array).
 * @param {string[]} tags
 * @param {string} tag
 * @returns {string[]}
 */
export function toggleTag(tags, tag) {
  return tags.includes(tag) ? tags.filter((t) => t !== tag) : [...tags, tag];
}

/**
 * Parse an event's string lat/lng into numbers, or null if absent/invalid.
 * @param {{location?: {lat?: string, lng?: string}}} event
 * @returns {{lat: number, lng: number}|null}
 */
export function coordsOf(event) {
  const loc = event?.location;
  if (!loc || loc.lat == null || loc.lng == null || loc.lat === '' || loc.lng === '') return null;
  const lat = Number(loc.lat);
  const lng = Number(loc.lng);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  if (Math.abs(lat) > 90 || Math.abs(lng) > 180) return null;
  return { lat, lng };
}

/**
 * Great-circle distance in km (haversine).
 * @param {{lat: number, lng: number}} a
 * @param {{lat: number, lng: number}} b
 * @returns {number}
 */
export function haversineKm(a, b) {
  const R = 6371;
  const rad = (d) => (d * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat);
  const dLng = rad(b.lng - a.lng);
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(s)));
}

/**
 * Sort events nearest-first from `origin`; events without coordinates go last (stable).
 * Returns copies annotated with `distanceKm` (null when unknown).
 * @param {object[]} events
 * @param {{lat: number, lng: number}} origin
 * @returns {object[]}
 */
export function sortByDistance(events, origin) {
  return events
    .map((e, i) => {
      const c = coordsOf(e);
      return { e: { ...e, distanceKm: c ? haversineKm(origin, c) : null }, i };
    })
    .sort((x, y) => {
      const dx = x.e.distanceKm ?? Infinity;
      const dy = y.e.distanceKm ?? Infinity;
      return dx === dy ? x.i - y.i : dx - dy;
    })
    .map((x) => x.e);
}

/**
 * Local-date key "YYYY-MM-DD".
 * @param {Date} d
 * @returns {string}
 */
export function dayKey(d) {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/**
 * Human label for a day relative to `now`: Today, Tomorrow, weekday (within a week), or date.
 * @param {Date} day
 * @param {Date} now
 * @param {string} [locale]
 * @returns {string}
 */
export function dayLabel(day, now, locale) {
  const startOf = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = Math.round((startOf(day) - startOf(now)) / 86400000);
  if (diff <= 0) return 'Today';
  if (diff === 1) return 'Tomorrow';
  if (diff < 7) return new Intl.DateTimeFormat(locale, { weekday: 'long' }).format(day);
  return new Intl.DateTimeFormat(locale, { weekday: 'short', month: 'short', day: 'numeric' }).format(day);
}

/**
 * Group events by local day. Events already in progress are grouped under today.
 * Groups are chronological; order within a group is preserved (e.g. distance order).
 * @param {object[]} events
 * @param {{now?: Date, locale?: string}} [opts]
 * @returns {{key: string, label: string, events: object[]}[]}
 */
export function groupByDay(events, { now = new Date(), locale } = {}) {
  const groups = new Map();
  for (const ev of events) {
    const start = new Date(ev.startsAt);
    const day = start < now ? now : start;
    const key = dayKey(day);
    if (!groups.has(key)) groups.set(key, { key, label: dayLabel(day, now, locale), events: [] });
    groups.get(key).events.push(ev);
  }
  return [...groups.values()].sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
}

/**
 * True when the event was edited after it was first indexed.
 * @param {{updatedAt?: string, indexedAt?: string}} event
 * @returns {boolean}
 */
export function isUpdated(event) {
  if (!event?.updatedAt || !event?.indexedAt) return false;
  return new Date(event.updatedAt) > new Date(event.indexedAt);
}
