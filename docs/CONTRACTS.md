# Contracts

The interfaces every module builds against. Change these only by agreement.

| Contract | File |
|---|---|
| Record schemas (on users' PDS) | `lexicons/*.json` |
| Domain models | `backend/app/models.py` |
| Storage interface | `backend/app/store/base.py` |
| Notifier interface | `backend/app/notify/base.py` |
| HTTP API | this file |

## HTTP API (JSON, camelCase)

`EventView` = `IndexedEvent` fields flattened: `{uri, cid, authorDid, authorHandle, source,
name, description, startsAt, endsAt, location:{name,address,lat,lng}, tags, group, sourceUrl,
createdAt, indexedAt, updatedAt, status}` where `status` is `upcoming | live | ending_soon` (ending within 1h).

| Method | Path | Body / Query | Returns |
|---|---|---|---|
| GET | `/api/health` | | `{ok:true}` |
| GET | `/api/config` | | `{devMode, jetstreamEnabled, eventNsid, listenerNsid}` |
| GET | `/api/events` | `tag` (repeatable, match any), `group`, `q`, `before`, `after` (ISO), `limit`, `cursor` | `{events:[EventView], cursor}` |
| GET | `/api/event` | `uri` | `EventView & {updates:[{text,sourceUri,createdAt}]}` or 404 |
| GET | `/api/tags` | | `[{value,count}]` |
| GET | `/api/groups` | | `[{value,count}]` |
| POST | `/api/subscriptions` | `{subscriberId, eventUri}` | 204 |
| DELETE | `/api/subscriptions` | `{subscriberId, eventUri}` | 204 |
| GET | `/api/subscriptions` | `subscriberId` | `[eventUri]` |
| GET | `/api/notifications` | `subscriberId`, `since` (id) | `[Notification]` |
| GET | `/api/notifications/stream` | `subscriberId` | SSE, `data: <Notification JSON>` per message |
| POST | `/api/import/ical` | `{url}` | `{imported:n}` |
| POST | `/api/dev/records` | Jetstream-shaped commit JSON (dev mode only) | `{ok:true}` |

Location privacy: the API never receives the user's position. "Near me" sorting happens in
the browser.

## Writes

Clients write directly to the user's PDS (`com.atproto.repo.createRecord` / `putRecord` /
`deleteRecord`) with collection `app.communitymap.event` or `app.communitymap.listener`.
The backend only *reads* the network (Jetstream) and builds the index. In dev mode the
frontend posts the same commit shape to `/api/dev/records` instead.

## Jetstream commit shape (input to ingest, and to `/api/dev/records`)

```json
{"did":"did:plc:abc","time_us":1731300000000000,"kind":"commit",
 "commit":{"operation":"create|update|delete","collection":"app.communitymap.event",
           "rkey":"3k...","cid":"bafy...","record":{...}}}
```
