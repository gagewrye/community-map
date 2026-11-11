/**
 * Anonymous event subscriptions + live notifications (SSE with reconnect and catch-up).
 * @module subscriptions
 */
import { getStorage, randomId, storageGet, storageSet } from './util.js';

const ID_KEY = 'cm:subscriber-id';
const LAST_KEY = 'cm:last-notification-id';
const ASKED_KEY = 'cm:notify-asked';

/**
 * Get (or create and persist) the anonymous subscriber id.
 * @param {Storage|null} storage
 * @returns {string}
 */
export function getSubscriberId(storage) {
  let id = storageGet(storage, ID_KEY);
  if (!id) {
    id = globalThis.crypto?.randomUUID?.() ?? randomId(24);
    storageSet(storage, ID_KEY, id);
  }
  return id;
}

/**
 * Pure catch-up merge: keep notifications newer than `lastId`, sorted by id, deduped.
 * @param {number|null} lastId
 * @param {{id: number}[]} list
 * @returns {{fresh: object[], lastId: number|null}}
 */
export function mergeNotifications(lastId, list) {
  const seen = new Set();
  const fresh = (list || [])
    .filter((n) => typeof n.id === 'number' && (lastId == null || n.id > lastId))
    .filter((n) => !seen.has(n.id) && seen.add(n.id))
    .sort((a, b) => a.id - b.id);
  const next = fresh.length ? fresh[fresh.length - 1].id : lastId;
  return { fresh, lastId: next };
}

/**
 * Backoff delay for reconnect attempt `n` (0-based): 1s, 2s, 4s… capped.
 * @param {number} n @param {number} [baseMs] @param {number} [maxMs]
 * @returns {number}
 */
export function backoffMs(n, baseMs = 1000, maxMs = 30000) {
  return Math.min(maxMs, baseMs * 2 ** n);
}

/**
 * @param {{api: ReturnType<typeof import('./api.js').createApi>,
 *   storage?: Storage|null, EventSourceImpl?: typeof EventSource|null,
 *   NotificationImpl?: typeof Notification|null, toast?: (msg: string) => void,
 *   onNotification?: (n: object) => void, onChange?: (subscribed: Set<string>) => void,
 *   baseDelayMs?: number}} opts
 */
export function createSubscriptions({
  api,
  storage = getStorage('localStorage'),
  EventSourceImpl = globalThis.EventSource ?? null,
  NotificationImpl = globalThis.Notification ?? null,
  toast = () => {},
  onNotification = () => {},
  onChange = () => {},
  baseDelayMs = 1000,
}) {
  const subscriberId = getSubscriberId(storage);
  const subscribed = new Set();
  let lastId = parseLast(storageGet(storage, LAST_KEY));
  let source = null;
  let attempts = 0;
  let timer = null;

  function parseLast(v) {
    const n = v == null ? NaN : Number(v);
    return Number.isFinite(n) ? n : null;
  }

  function setLast(id) {
    lastId = id;
    storageSet(storage, LAST_KEY, id == null ? null : String(id));
  }

  function deliver(n) {
    toast(n.message);
    const hidden = globalThis.document?.hidden;
    if (hidden && NotificationImpl?.permission === 'granted') {
      try {
        new NotificationImpl('Community Map', { body: n.message, tag: `cm-${n.id}` });
      } catch {
        /* some platforms only allow notifications from a service worker */
      }
    }
    onNotification(n);
  }

  function handle(list) {
    const { fresh, lastId: next } = mergeNotifications(lastId, list);
    setLast(next);
    fresh.forEach(deliver);
  }

  /** Fetch notifications missed while disconnected. First run only records a baseline. */
  async function catchUp() {
    try {
      const { data } = await api.notifications(subscriberId, lastId);
      if (lastId == null) {
        setLast(mergeNotifications(null, data).lastId ?? 0);
        return;
      }
      handle(data);
    } catch {
      /* offline; next reconnect retries */
    }
  }

  function connect() {
    if (!EventSourceImpl || source || subscribed.size === 0) return;
    clearTimeout(timer);
    source = new EventSourceImpl(api.notificationStreamUrl(subscriberId));
    source.onopen = () => {
      attempts = 0;
      catchUp();
    };
    source.onmessage = (ev) => {
      try {
        handle([JSON.parse(ev.data)]);
      } catch {
        /* ignore malformed message */
      }
    };
    source.onerror = () => {
      disconnect();
      timer = setTimeout(connect, backoffMs(attempts++, baseDelayMs));
    };
  }

  function disconnect() {
    clearTimeout(timer);
    if (source) source.close();
    source = null;
  }

  async function askPermissionOnce() {
    if (!NotificationImpl || NotificationImpl.permission !== 'default') return;
    if (storageGet(storage, ASKED_KEY)) return;
    storageSet(storage, ASKED_KEY, '1');
    try {
      await NotificationImpl.requestPermission();
    } catch {
      /* ignore */
    }
  }

  function changed() {
    onChange(new Set(subscribed));
    if (subscribed.size) connect();
    else disconnect();
  }

  return {
    subscriberId,
    /** @returns {Set<string>} copy of subscribed event URIs */
    get subscribed() {
      return new Set(subscribed);
    },
    /** @param {string} uri @returns {boolean} */
    has: (uri) => subscribed.has(uri),
    /** Load the server's subscription list and connect the stream if needed. */
    async load() {
      try {
        const { data } = await api.listSubscriptions(subscriberId);
        subscribed.clear();
        (data || []).forEach((u) => subscribed.add(u));
      } catch {
        /* offline with no cache */
      }
      changed();
    },
    /**
     * Toggle a subscription. Asks for Notification permission on the very first subscribe.
     * @param {string} uri
     * @returns {Promise<boolean>} new subscribed state
     */
    async toggle(uri) {
      if (subscribed.has(uri)) {
        await api.unsubscribe(subscriberId, uri);
        subscribed.delete(uri);
      } else {
        await api.subscribe(subscriberId, uri);
        subscribed.add(uri);
        askPermissionOnce();
      }
      changed();
      return subscribed.has(uri);
    },
    /** Reconnect immediately (e.g. on the window "online" event). */
    reconnectNow() {
      attempts = 0;
      disconnect();
      connect();
    },
    catchUp,
    disconnect,
  };
}
