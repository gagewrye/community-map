/**
 * HTTP client for the Community Map AppView (docs/CONTRACTS.md).
 *
 * Every GET resolves to `{data, stale}`. On network failure, timeout or 5xx, a GET falls
 * back to the last cached response with `stale: true` (and `savedAt`). Writes never fall back.
 * @module api
 */
import { createCache } from './cache.js';

/** Error for non-2xx responses (and offline with nothing cached). */
export class ApiError extends Error {
  /**
   * @param {string} message
   * @param {{status?: number, body?: any, offline?: boolean}} [info]
   */
  constructor(message, { status = 0, body = null, offline = false } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
    this.offline = offline;
  }
}

/**
 * Serialize params; arrays become repeated keys, empty values are dropped.
 * @param {Record<string, any>} [params]
 * @returns {string} query string including leading "?" (or "")
 */
export function toQueryString(params = {}) {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    for (const item of Array.isArray(v) ? v : [v]) {
      if (item != null && item !== '') sp.append(k, String(item));
    }
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

/**
 * @typedef {{data: any, stale: boolean, savedAt?: number}} GetResult
 */

/**
 * Create the API client.
 * @param {{baseUrl?: string, fetchImpl?: typeof fetch, cache?: import('./cache.js').Cache,
 *          timeoutMs?: number}} [opts]
 */
export function createApi({ baseUrl = '', fetchImpl = (...a) => fetch(...a), cache = createCache(), timeoutMs = 8000 } = {}) {
  const root = baseUrl.replace(/\/$/, '');
  const url = (path, params) => `${root}${path}${toQueryString(params)}`;

  async function request(method, target, body) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const init = { method, signal: ctrl.signal, headers: { Accept: 'application/json' } };
      if (body !== undefined) {
        init.headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(body);
      }
      return await fetchImpl(target, init);
    } finally {
      clearTimeout(timer);
    }
  }

  async function parse(res) {
    if (res.status === 204) return null;
    const text = await res.text();
    return text ? JSON.parse(text) : null;
  }

  async function errorFrom(res) {
    let body = null;
    try {
      body = await parse(res);
    } catch {
      /* non-JSON error body */
    }
    return new ApiError(`HTTP ${res.status}`, { status: res.status, body });
  }

  /** GET with cache write-through and stale fallback. */
  async function get(path, params, { useCache = true } = {}) {
    const target = url(path, params);
    let res;
    try {
      res = await request('GET', target);
    } catch (err) {
      return fallback(target, useCache, err);
    }
    if (res.status >= 500) return fallback(target, useCache, await errorFrom(res));
    if (!res.ok) throw await errorFrom(res);
    const data = await parse(res);
    // The service worker marks responses it served from its own cache.
    const swStale = res.headers?.get?.('x-cm-stale') === '1';
    if (useCache && !swStale) cache.set(target, data);
    return swStale ? { data, stale: true } : { data, stale: false };
  }

  function fallback(target, useCache, err) {
    const hit = useCache ? cache.get(target) : null;
    if (hit) return { data: hit.value, stale: true, savedAt: hit.savedAt };
    if (err instanceof ApiError) throw err;
    throw new ApiError('Network unavailable', { offline: true });
  }

  async function send(method, path, body) {
    let res;
    try {
      res = await request(method, url(path), body);
    } catch {
      throw new ApiError('Network unavailable', { offline: true });
    }
    if (!res.ok) throw await errorFrom(res);
    return parse(res);
  }

  return {
    /** @returns {Promise<GetResult>} `{ok:true}` */
    health: () => get('/api/health', undefined, { useCache: false }),
    /** @returns {Promise<GetResult>} `{devMode, jetstreamEnabled, eventNsid, listenerNsid}` */
    config: () => get('/api/config'),
    /**
     * @param {{tag?: string[], group?: string, q?: string, before?: string, after?: string,
     *          limit?: number, cursor?: string}} [params]
     * @returns {Promise<GetResult>} `{events, cursor}`
     */
    listEvents: (params) => get('/api/events', params),
    /** @param {string} uri @returns {Promise<GetResult>} EventView & {updates} */
    getEvent: (uri) => get('/api/event', { uri }),
    /** @returns {Promise<GetResult>} `[{value,count}]` */
    tags: () => get('/api/tags'),
    /** @returns {Promise<GetResult>} `[{value,count}]` */
    groups: () => get('/api/groups'),
    /** @param {string} subscriberId @param {string} eventUri */
    subscribe: (subscriberId, eventUri) => send('POST', '/api/subscriptions', { subscriberId, eventUri }),
    /** @param {string} subscriberId @param {string} eventUri */
    unsubscribe: (subscriberId, eventUri) => send('DELETE', '/api/subscriptions', { subscriberId, eventUri }),
    /** @param {string} subscriberId @returns {Promise<GetResult>} `[eventUri]` */
    listSubscriptions: (subscriberId) => get('/api/subscriptions', { subscriberId }),
    /**
     * @param {string} subscriberId @param {number|null} [since] notification id
     * @returns {Promise<GetResult>} `[Notification]` (never served from cache)
     */
    notifications: (subscriberId, since) =>
      get('/api/notifications', { subscriberId, since }, { useCache: false }),
    /** @param {string} subscriberId @returns {string} SSE URL for EventSource */
    notificationStreamUrl: (subscriberId) => url('/api/notifications/stream', { subscriberId }),
    /** @param {string} icalUrl @returns {Promise<{imported:number}>} */
    importIcal: (icalUrl) => send('POST', '/api/import/ical', { url: icalUrl }),
    /** @param {object} commit Jetstream-shaped commit @returns {Promise<{ok:true}>} */
    postDevRecord: (commit) => send('POST', '/api/dev/records', commit),
  };
}
