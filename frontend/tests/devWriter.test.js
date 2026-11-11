import { describe, expect, it, vi } from 'vitest';
import { buildCommit, createDevWriter, generateTid } from '../src/devWriter.js';
import { memoryStorage } from './helpers.js';

describe('generateTid', () => {
  it('is 13 base32-sortable chars and monotonic', () => {
    const a = generateTid(1731300000000);
    const b = generateTid(1731300000000);
    const c = generateTid(1731300005000);
    for (const t of [a, b, c]) expect(t).toMatch(/^[234567a-z]{13}$/);
    expect(a < b && b < c).toBe(true);
  });
});

describe('dev writer', () => {
  it('posts Jetstream-shaped create commits with a persisted fake DID', async () => {
    const api = { postDevRecord: vi.fn(async () => ({ ok: true })) };
    const storage = memoryStorage();
    const w = createDevWriter({ api, storage });
    expect(w.did).toMatch(/^did:plc:demo-[a-z2-7]+$/);
    expect(createDevWriter({ api, storage }).did).toBe(w.did);

    const res = await w.createEvent({ name: 'Jam', createdAt: '2026-11-11T00:00:00Z' });
    const c = api.postDevRecord.mock.calls[0][0];
    expect(c).toEqual({
      did: w.did, time_us: expect.any(Number), kind: 'commit',
      commit: { operation: 'create', collection: 'app.communitymap.event', rkey: expect.stringMatching(/^[234567a-z]{13}$/),
        cid: expect.stringMatching(/^bafy/), record: { $type: 'app.communitymap.event', name: 'Jam', createdAt: '2026-11-11T00:00:00Z' } },
    });
    expect(res.uri).toBe(`at://${w.did}/app.communitymap.event/${c.commit.rkey}`);
  });

  it('update keeps rkey; delete has no record/cid; listener uses listener collection', async () => {
    const api = { postDevRecord: vi.fn(async () => ({ ok: true })) };
    const w = createDevWriter({ api, storage: memoryStorage() });
    await w.updateEvent('3kabc', { name: 'n' });
    await w.deleteEvent('3kabc');
    await w.createListener('at://x/app.communitymap.event/3kabc', 'Tag');
    const [u, d, l] = api.postDevRecord.mock.calls.map((x) => x[0].commit);
    expect(u).toMatchObject({ operation: 'update', rkey: '3kabc', record: { name: 'n' } });
    expect(d).toEqual({ operation: 'delete', collection: 'app.communitymap.event', rkey: '3kabc' });
    expect(l).toMatchObject({ operation: 'create', collection: 'app.communitymap.listener', record: { subject: 'at://x/app.communitymap.event/3kabc', hashtag: 'tag' } });
  });

  it('buildCommit uses microsecond time', () => {
    expect(buildCommit({ did: 'd', operation: 'delete', collection: 'c', rkey: 'r', nowMs: 1731300000000 }).time_us).toBe(1731300000000000);
  });
});
