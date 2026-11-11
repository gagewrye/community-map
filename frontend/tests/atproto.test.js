import { describe, expect, it, vi } from 'vitest';
import { createAtprotoWriter, didDocUrl, pdsFromDidDoc } from '../src/atproto.js';
import { buildEventRecord } from '../src/records.js';
import { jsonResponse, memoryStorage } from './helpers.js';

const DID = 'did:plc:alice123';
const PDS = 'https://pds.example.com';
const didDoc = { id: DID, service: [{ id: '#atproto_pds', type: 'AtprotoPersonalDataServer', serviceEndpoint: `${PDS}/` }] };

function fakeNetwork(overrides = {}) {
  const routes = {
    'https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle?handle=alice.test': () => jsonResponse({ did: DID }),
    [`https://plc.directory/${DID}`]: () => jsonResponse(didDoc),
    [`${PDS}/xrpc/com.atproto.server.createSession`]: () => jsonResponse({ did: DID, handle: 'alice.test', accessJwt: 'A1', refreshJwt: 'R1' }),
    [`${PDS}/xrpc/com.atproto.repo.createRecord`]: () => jsonResponse({ uri: `at://${DID}/app.communitymap.event/3kxyz`, cid: 'bafyc' }),
    [`${PDS}/xrpc/com.atproto.repo.putRecord`]: () => jsonResponse({ uri: 'u', cid: 'c' }),
    [`${PDS}/xrpc/com.atproto.repo.deleteRecord`]: () => jsonResponse({}),
    ...overrides,
  };
  return vi.fn(async (url) => {
    const r = routes[url];
    if (!r) return jsonResponse({ error: 'NotFound' }, 404);
    return r();
  });
}

const body = (call) => JSON.parse(call[1].body);

describe('atproto helpers', () => {
  it('resolves DID document URLs for plc and web', () => {
    expect(didDocUrl('did:plc:x')).toBe('https://plc.directory/did:plc:x');
    expect(didDocUrl('did:web:ucsd.edu')).toBe('https://ucsd.edu/.well-known/did.json');
    expect(didDocUrl('did:web:localhost%3A3000:u:bob')).toBe('https://localhost:3000/u/bob/did.json');
    expect(() => didDocUrl('did:key:z')).toThrow();
  });

  it('finds the PDS service endpoint', () => {
    expect(pdsFromDidDoc(didDoc)).toBe(PDS);
    expect(pdsFromDidDoc({ service: [] })).toBeNull();
  });
});

describe('atproto writer', () => {
  it('login: resolveHandle → DID doc → createSession, persisted to sessionStorage', async () => {
    const f = fakeNetwork();
    const storage = memoryStorage();
    const w = createAtprotoWriter({ fetchImpl: f, storage });
    expect(await w.login('@alice.test', 'app-pw')).toEqual({ did: DID, handle: 'alice.test' });
    expect(f.mock.calls.map((c) => c[0])).toEqual([
      'https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle?handle=alice.test',
      `https://plc.directory/${DID}`,
      `${PDS}/xrpc/com.atproto.server.createSession`,
    ]);
    expect(body(f.mock.calls[2])).toEqual({ identifier: 'alice.test', password: 'app-pw' });
    expect(w.did).toBe(DID);
    // restored by a new instance from the same sessionStorage
    expect(createAtprotoWriter({ fetchImpl: f, storage }).loggedIn).toBe(true);
  });

  it('falls back to the second resolver', async () => {
    const f = fakeNetwork({
      'https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle?handle=alice.test': () => { throw new TypeError('net'); },
      'https://bsky.social/xrpc/com.atproto.identity.resolveHandle?handle=alice.test': () => jsonResponse({ did: DID }),
    });
    const w = createAtprotoWriter({ fetchImpl: f, storage: memoryStorage() });
    await w.login('alice.test', 'pw');
    expect(w.did).toBe(DID);
  });

  it('createEvent sends a lexicon-exact createRecord payload with bearer auth', async () => {
    const f = fakeNetwork();
    const w = createAtprotoWriter({ fetchImpl: f, storage: memoryStorage() });
    await w.login('alice.test', 'pw');
    const record = buildEventRecord({ name: 'Jam', startsAt: '2026-11-12T18:00:00.000Z', endsAt: '2026-11-12T20:00:00.000Z', locationName: 'Geisel', lat: 32.88, lng: -117.23, tags: 'study' });
    const res = await w.createEvent(record);
    expect(res.uri).toBe(`at://${DID}/app.communitymap.event/3kxyz`);
    const call = f.mock.calls.at(-1);
    expect(call[1].headers.Authorization).toBe('Bearer A1');
    expect(body(call)).toEqual({
      repo: DID,
      collection: 'app.communitymap.event',
      record: {
        $type: 'app.communitymap.event', name: 'Jam', startsAt: '2026-11-12T18:00:00.000Z', endsAt: '2026-11-12T20:00:00.000Z',
        location: { name: 'Geisel', lat: '32.88', lng: '-117.23' }, tags: ['study'], createdAt: record.createdAt,
      },
    });
  });

  it('updateEvent uses putRecord with rkey; deleteEvent uses deleteRecord; createListener', async () => {
    const f = fakeNetwork();
    const w = createAtprotoWriter({ fetchImpl: f, storage: memoryStorage() });
    await w.login('alice.test', 'pw');
    await w.updateEvent('3kxyz', { name: 'n' });
    expect(body(f.mock.calls.at(-1))).toMatchObject({ repo: DID, collection: 'app.communitymap.event', rkey: '3kxyz', record: { $type: 'app.communitymap.event', name: 'n' } });
    expect(await w.deleteEvent('3kxyz')).toEqual({ uri: `at://${DID}/app.communitymap.event/3kxyz` });
    expect(body(f.mock.calls.at(-1))).toEqual({ repo: DID, collection: 'app.communitymap.event', rkey: '3kxyz' });
    await w.createListener(`at://${DID}/app.communitymap.event/3kxyz`, '#StudyJam');
    const l = body(f.mock.calls.at(-1));
    expect(l.collection).toBe('app.communitymap.listener');
    expect(l.record).toEqual({ $type: 'app.communitymap.listener', subject: `at://${DID}/app.communitymap.event/3kxyz`, hashtag: 'studyjam', createdAt: l.record.createdAt });
  });

  it('refreshes the session on ExpiredToken and retries once', async () => {
    let first = true;
    const f = fakeNetwork({
      [`${PDS}/xrpc/com.atproto.repo.createRecord`]: () => {
        if (first) { first = false; return jsonResponse({ error: 'ExpiredToken', message: 'Token has expired' }, 401); }
        return jsonResponse({ uri: 'u2', cid: 'c2' });
      },
      [`${PDS}/xrpc/com.atproto.server.refreshSession`]: () => jsonResponse({ did: DID, handle: 'alice.test', accessJwt: 'A2', refreshJwt: 'R2' }),
    });
    const w = createAtprotoWriter({ fetchImpl: f, storage: memoryStorage() });
    await w.login('alice.test', 'pw');
    expect(await w.createEvent({ name: 'x' })).toEqual({ uri: 'u2', cid: 'c2' });
    const urls = f.mock.calls.map((c) => c[0]).slice(3);
    expect(urls).toEqual([`${PDS}/xrpc/com.atproto.repo.createRecord`, `${PDS}/xrpc/com.atproto.server.refreshSession`, `${PDS}/xrpc/com.atproto.repo.createRecord`]);
    expect(f.mock.calls[4][1].headers.Authorization).toBe('Bearer R1');
    expect(f.mock.calls[5][1].headers.Authorization).toBe('Bearer A2');
  });

  it('surfaces login errors and supports logout', async () => {
    const f = fakeNetwork({ [`${PDS}/xrpc/com.atproto.server.createSession`]: () => jsonResponse({ error: 'AuthenticationRequired', message: 'Invalid identifier or password' }, 401) });
    const w = createAtprotoWriter({ fetchImpl: f, storage: memoryStorage() });
    await expect(w.login('alice.test', 'bad')).rejects.toThrow('Invalid identifier or password');
    expect(w.loggedIn).toBe(false);
    const ok = createAtprotoWriter({ fetchImpl: fakeNetwork(), storage: memoryStorage() });
    await ok.login('alice.test', 'pw');
    await ok.logout();
    expect(ok.loggedIn).toBe(false);
  });
});
