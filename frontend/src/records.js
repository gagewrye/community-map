/**
 * Lexicon record building + validation (mirrors lexicons/*.json), shared by both writers.
 * @module records
 */

export const EVENT_NSID = 'app.communitymap.event';
export const LISTENER_NSID = 'app.communitymap.listener';

const bytes = (s) => new TextEncoder().encode(s).length; // lexicon maxLength = UTF-8 bytes

/**
 * Normalize a comma-separated tag string (strip "#", lowercase, dedupe), like the backend.
 * @param {string|string[]} input
 * @returns {string[]}
 */
export function parseTags(input) {
  const parts = Array.isArray(input) ? input : String(input || '').split(',');
  const out = [];
  for (const raw of parts) {
    const t = raw.trim().replace(/^#+/, '').toLowerCase();
    if (t && !out.includes(t)) out.push(t);
  }
  return out;
}

/**
 * Build an app.communitymap.event record from form-ish input. Optional empty fields are
 * omitted; lat/lng become strings; `createdAt` defaults to now.
 * @param {{name: string, description?: string, startsAt: string, endsAt: string,
 *   locationName: string, address?: string, lat?: string|number, lng?: string|number,
 *   tags?: string|string[], group?: string, sourceUrl?: string, createdAt?: string}} input
 * @returns {object}
 */
export function buildEventRecord(input) {
  const str = (v) => (v == null ? '' : String(v).trim());
  const location = { name: str(input.locationName) };
  if (str(input.address)) location.address = str(input.address);
  if (str(input.lat) !== '' && str(input.lng) !== '') {
    location.lat = String(Number(str(input.lat)));
    location.lng = String(Number(str(input.lng)));
  }
  const record = {
    $type: EVENT_NSID,
    name: str(input.name),
    startsAt: input.startsAt,
    endsAt: input.endsAt,
    location,
    createdAt: input.createdAt || new Date().toISOString(),
  };
  if (str(input.description)) record.description = str(input.description);
  const tags = parseTags(input.tags || []);
  if (tags.length) record.tags = tags;
  if (str(input.group)) record.group = str(input.group);
  if (str(input.sourceUrl)) record.sourceUrl = str(input.sourceUrl);
  return record;
}

/**
 * Build an app.communitymap.listener record.
 * @param {string} subject at:// URI of the event
 * @param {string} hashtag with or without leading "#"
 * @returns {object}
 */
export function buildListenerRecord(subject, hashtag) {
  return {
    $type: LISTENER_NSID,
    subject,
    hashtag: String(hashtag).trim().replace(/^#+/, '').toLowerCase(),
    createdAt: new Date().toISOString(),
  };
}

const isDate = (s) => typeof s === 'string' && s !== '' && !Number.isNaN(Date.parse(s));

/**
 * Validate an event record against the lexicon. Returns field → message (empty = valid).
 * Field keys: name, description, startsAt, endsAt, locationName, address, coords, tags, group.
 * @param {object} r event record
 * @returns {Record<string, string>}
 */
export function validateEventRecord(r) {
  const e = {};
  if (!r.name) e.name = 'Name is required.';
  else if (bytes(r.name) > 200) e.name = 'Name is too long (max 200).';
  if (r.description && bytes(r.description) > 3000) e.description = 'Description is too long (max 3000).';
  if (!isDate(r.startsAt)) e.startsAt = 'Start time is required.';
  if (!isDate(r.endsAt)) e.endsAt = 'End time is required.';
  else if (isDate(r.startsAt) && Date.parse(r.endsAt) < Date.parse(r.startsAt)) {
    e.endsAt = 'End must be at or after start.';
  }
  const loc = r.location || {};
  if (!loc.name) e.locationName = 'Location name is required.';
  else if (bytes(loc.name) > 200) e.locationName = 'Location name is too long (max 200).';
  if (loc.address && bytes(loc.address) > 300) e.address = 'Address is too long (max 300).';
  const coordsErr = validateCoords(loc.lat, loc.lng);
  if (coordsErr) e.coords = coordsErr;
  const tags = r.tags || [];
  if (tags.length > 10) e.tags = 'At most 10 tags.';
  else if (tags.some((t) => bytes(t) > 32)) e.tags = 'Each tag must be 32 characters or fewer.';
  if (r.group && bytes(r.group) > 100) e.group = 'Group is too long (max 100).';
  return e;
}

function validateCoords(lat, lng) {
  if (lat == null && lng == null) return null;
  if (lat == null || lng == null) return 'Enter both latitude and longitude, or neither.';
  const a = Number(lat);
  const b = Number(lng);
  if (!Number.isFinite(a) || Math.abs(a) > 90) return 'Latitude must be between -90 and 90.';
  if (!Number.isFinite(b) || Math.abs(b) > 180) return 'Longitude must be between -180 and 180.';
  return null;
}

/**
 * Validate a hashtag for a listener record ("" means none, which is valid).
 * @param {string} tag
 * @returns {string|null} error message
 */
export function validateHashtag(tag) {
  const t = String(tag || '').trim().replace(/^#+/, '');
  if (!t) return null;
  if (bytes(t) > 64) return 'Hashtag is too long (max 64).';
  if (/\s/.test(t)) return 'Hashtag cannot contain spaces.';
  return null;
}

/**
 * Parse an at:// URI.
 * @param {string} uri
 * @returns {{did: string, collection: string, rkey: string}|null}
 */
export function parseAtUri(uri) {
  const m = /^at:\/\/([^/]+)\/([^/]+)\/([^/?#]+)$/.exec(uri || '');
  return m ? { did: m[1], collection: m[2], rkey: m[3] } : null;
}
