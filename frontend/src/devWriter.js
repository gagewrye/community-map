/**
 * "Demo mode" writer: same interface as the atproto writer, but posts Jetstream-shaped
 * commits to POST /api/dev/records under a fake, locally persisted DID.
 * @module devWriter
 */
import { EVENT_NSID, LISTENER_NSID, buildListenerRecord } from './records.js';
import { getStorage, randomId, storageGet, storageSet } from './util.js';

const DID_KEY = 'cm:demo-did';
const S32 = '234567abcdefghijklmnopqrstuvwxyz';

let lastTidUs = 0n;
const clockId = BigInt(Math.floor(Math.random() * 1024));

/**
 * Generate a TID-like record key: 13 chars of base32-sortable encoding of
 * (microsecond timestamp << 10 | clock id). Monotonic within this page.
 * @param {number} [nowMs]
 * @returns {string}
 */
export function generateTid(nowMs = Date.now()) {
  let us = BigInt(Math.floor(nowMs)) * 1000n;
  if (us <= lastTidUs) us = lastTidUs + 1n;
  lastTidUs = us;
  let n = ((us & ((1n << 53n) - 1n)) << 10n) | clockId;
  let out = '';
  for (let i = 0; i < 13; i++) {
    out = S32[Number(n & 31n)] + out;
    n >>= 5n;
  }
  return out;
}

/**
 * Build a Jetstream-shaped commit (see CONTRACTS.md).
 * @param {{did: string, operation: 'create'|'update'|'delete', collection: string,
 *   rkey: string, record?: object, nowMs?: number}} p
 * @returns {object}
 */
export function buildCommit({ did, operation, collection, rkey, record, nowMs = Date.now() }) {
  const commit = { operation, collection, rkey };
  if (operation !== 'delete') {
    commit.cid = `bafydev${randomId(24)}`;
    commit.record = record;
  }
  return { did, time_us: Math.floor(nowMs) * 1000, kind: 'commit', commit };
}

/**
 * @param {{api: {postDevRecord(c: object): Promise<any>}, storage?: Storage|null}} opts
 */
export function createDevWriter({ api, storage = getStorage('localStorage') }) {
  let did = storageGet(storage, DID_KEY);
  if (!did) {
    did = `did:plc:demo-${randomId(12)}`;
    storageSet(storage, DID_KEY, did);
  }

  async function commit(operation, collection, rkey, record) {
    const c = buildCommit({ did, operation, collection, rkey, record });
    await api.postDevRecord(c);
    return { uri: `at://${did}/${collection}/${rkey}`, cid: c.commit.cid };
  }

  return {
    kind: 'dev',
    did,
    handle: 'demo',
    loggedIn: false,
    /** @param {object} record @returns {Promise<{uri: string, cid: string}>} */
    createEvent: (record) => commit('create', EVENT_NSID, generateTid(), { ...record, $type: EVENT_NSID }),
    /** @param {string} rkey @param {object} record */
    updateEvent: (rkey, record) => commit('update', EVENT_NSID, rkey, { ...record, $type: EVENT_NSID }),
    /** @param {string} rkey */
    deleteEvent: (rkey) => commit('delete', EVENT_NSID, rkey),
    /** @param {string} eventUri @param {string} hashtag */
    createListener: (eventUri, hashtag) =>
      commit('create', LISTENER_NSID, generateTid(), buildListenerRecord(eventUri, hashtag)),
  };
}
