import { describe, expect, it, vi } from 'vitest';
import { backoffMs, createSubscriptions, getSubscriberId, mergeNotifications } from '../src/subscriptions.js';
import { memoryStorage } from './helpers.js';

const n = (id, message = `m${id}`) => ({ id, subscriberId: 's', eventUri: 'at://e', kind: 'announcement', message, createdAt: '2026-11-11T00:00:00Z' });

class FakeES {
  static instances = [];
  constructor(url) { this.url = url; this.closed = false; FakeES.instances.push(this); }
  close() { this.closed = true; }
}

function setup({ storage = memoryStorage(), notifications = [] } = {}) {
  FakeES.instances = [];
  const api = {
    listSubscriptions: vi.fn(async () => ({ data: ['at://e'], stale: false })),
    subscribe: vi.fn(async () => null),
    unsubscribe: vi.fn(async () => null),
    notifications: vi.fn(async () => ({ data: notifications, stale: false })),
    notificationStreamUrl: (id) => `/api/notifications/stream?subscriberId=${id}`,
  };
  const toast = vi.fn();
  const NotificationImpl = Object.assign(vi.fn(), { permission: 'default', requestPermission: vi.fn(async () => 'granted') });
  const subs = createSubscriptions({ api, storage, EventSourceImpl: FakeES, NotificationImpl, toast, baseDelayMs: 10 });
  return { api, toast, subs, storage, NotificationImpl };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

describe('mergeNotifications', () => {
  it('keeps only newer, deduped, sorted; advances lastId', () => {
    expect(mergeNotifications(5, [n(7), n(4), n(6), n(7), n(5)])).toEqual({ fresh: [n(6), n(7)], lastId: 7 });
    expect(mergeNotifications(5, [])).toEqual({ fresh: [], lastId: 5 });
    expect(mergeNotifications(null, [n(2), n(1)]).lastId).toBe(2);
  });

  it('backoff doubles and caps', () => {
    expect([0, 1, 2, 10].map((i) => backoffMs(i, 1000, 30000))).toEqual([1000, 2000, 4000, 30000]);
  });
});

describe('subscriptions', () => {
  it('persists an anonymous subscriberId', () => {
    const s = memoryStorage();
    const id = getSubscriberId(s);
    expect(id).toBeTruthy();
    expect(getSubscriberId(s)).toBe(id);
  });

  it('subscribe/unsubscribe call the API; permission is requested only once', async () => {
    const { api, subs, NotificationImpl } = setup();
    await subs.toggle('at://a');
    expect(api.subscribe).toHaveBeenCalledWith(subs.subscriberId, 'at://a');
    expect(subs.has('at://a')).toBe(true);
    await subs.toggle('at://a');
    expect(api.unsubscribe).toHaveBeenCalledWith(subs.subscriberId, 'at://a');
    expect(subs.has('at://a')).toBe(false);
    await subs.toggle('at://b');
    expect(NotificationImpl.requestPermission).toHaveBeenCalledTimes(1);
  });

  it('opens the stream only while subscribed and toasts messages', async () => {
    const { subs, toast } = setup();
    await subs.load();
    expect(FakeES.instances).toHaveLength(1);
    expect(FakeES.instances[0].url).toContain(`subscriberId=${subs.subscriberId}`);
    FakeES.instances[0].onmessage({ data: JSON.stringify(n(1, 'Room changed')) });
    expect(toast).toHaveBeenCalledWith('Room changed');
    await subs.toggle('at://e');
    expect(FakeES.instances[0].closed).toBe(true);
  });

  it('first connect records a baseline silently', async () => {
    const { subs, toast, api, storage } = setup({ notifications: [n(3), n(4)] });
    await subs.load();
    FakeES.instances[0].onopen();
    await flush();
    expect(api.notifications).toHaveBeenCalledWith(subs.subscriberId, null);
    expect(toast).not.toHaveBeenCalled();
    expect(storage.getItem('cm:last-notification-id')).toBe('4');
  });

  it('on reconnect, catches up via since=<lastId> without duplicating stream messages', async () => {
    vi.useFakeTimers();
    const { subs, toast, api } = setup();
    await subs.load();
    const es1 = FakeES.instances[0];
    es1.onmessage({ data: JSON.stringify(n(10)) });
    es1.onerror();
    expect(es1.closed).toBe(true);
    await vi.advanceTimersByTimeAsync(10);
    const es2 = FakeES.instances[1];
    expect(es2).toBeDefined();
    api.notifications.mockResolvedValueOnce({ data: [n(10), n(11), n(12)], stale: false });
    es2.onopen();
    await vi.advanceTimersByTimeAsync(0);
    expect(api.notifications).toHaveBeenLastCalledWith(subs.subscriberId, 10);
    expect(toast.mock.calls.map((c) => c[0])).toEqual(['m10', 'm11', 'm12']);
    es2.onmessage({ data: JSON.stringify(n(12)) });
    expect(toast).toHaveBeenCalledTimes(3);
    vi.useRealTimers();
  });
});
