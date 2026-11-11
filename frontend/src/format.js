/**
 * Display formatting shared by views (dates in the user's local time zone).
 * @module format
 */
import { coordsOf, dayKey } from './filters.js';

/**
 * Format a start–end window, e.g. "3:00 PM – 5:00 PM" or with dates when multi-day.
 * @param {string} startsAt ISO
 * @param {string} endsAt ISO
 * @param {{locale?: string, timeZone?: string}} [opts]
 * @returns {string}
 */
export function formatTimeWindow(startsAt, endsAt, { locale, timeZone } = {}) {
  const s = new Date(startsAt);
  const e = new Date(endsAt);
  const time = new Intl.DateTimeFormat(locale, { hour: 'numeric', minute: '2-digit', timeZone });
  const full = new Intl.DateTimeFormat(locale, {
    weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone,
  });
  const sameDay = timeZone ? sameDayInZone(s, e, timeZone) : dayKey(s) === dayKey(e);
  return sameDay ? `${time.format(s)} – ${time.format(e)}` : `${full.format(s)} – ${full.format(e)}`;
}

function sameDayInZone(a, b, timeZone) {
  const f = new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' });
  return f.format(a) === f.format(b);
}

/**
 * Format a single timestamp (e.g. for announcements).
 * @param {string} iso @param {{locale?: string, timeZone?: string}} [opts]
 * @returns {string}
 */
export function formatDateTime(iso, { locale, timeZone } = {}) {
  return new Intl.DateTimeFormat(locale, {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone,
  }).format(new Date(iso));
}

/**
 * OpenStreetMap link: exact pin when lat/lng exist, else an address search, else null.
 * @param {object} event
 * @returns {string|null}
 */
export function osmUrl(event) {
  const c = coordsOf(event);
  if (c) return `https://www.openstreetmap.org/?mlat=${c.lat}&mlon=${c.lng}#map=18/${c.lat}/${c.lng}`;
  const addr = event?.location?.address;
  return addr ? `https://www.openstreetmap.org/search?query=${encodeURIComponent(addr)}` : null;
}

/**
 * Status badge text for EventView.status, or null for "upcoming".
 * @param {string} status
 * @returns {string|null}
 */
export function statusLabel(status) {
  return { live: 'Live', ending_soon: 'Ending soon' }[status] ?? null;
}

/**
 * Format a distance for display.
 * @param {number|null|undefined} km
 * @returns {string|null}
 */
export function formatDistance(km) {
  if (km == null) return null;
  return km < 1 ? `${Math.round(km * 1000)} m away` : `${km.toFixed(1)} km away`;
}
