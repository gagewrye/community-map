# Community Map

Campus events on the AT Protocol. Students browse a feed of events near UCSD, filter by tag or org, and subscribe to get live updates. Hosts post events with their Bluesky account, so the data lives in their own PDS and not in our database.

**Status:** working prototype. It has 98 backend tests and 81 frontend tests, and CI runs both.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -e "./backend[dev]"
cd backend
CM_DB_PATH=data/demo.db ../.venv/bin/python -m app.seed      # 12 sample UCSD events
CM_DB_PATH=data/demo.db CM_DEV_MODE=true ../.venv/bin/uvicorn app.main:app --reload
# open http://localhost:8000   (API docs: /docs)
```

`CM_DEV_MODE=true` turns on **Demo mode**: you can post events without a Bluesky account. Set `CM_JETSTREAM_ENABLED=true` to index real records from the network.

Tests: `cd backend && ../.venv/bin/pytest` · `cd frontend && npm ci && npm test`

## What it does

| Requirement (from the spec) | Where |
|---|---|
| Curated feed: list view first, filters by tag, group and text, "near me" | `frontend/src/views/listView.js`, `filterBar.js`, `GET /api/events` |
| Map of events/POIs (secondary tab, loaded on demand) | `frontend/src/views/mapView.js` (Leaflet + OSM; tile URL is configurable) |
| Hosts post events with a time window and location | `frontend/src/atproto.js` writes `app.communitymap.event` to the user's PDS |
| Events expire gracefully | Badges show "Ending soon", subscribers get an "ended" notice, then `backend/app/expiry.py` removes the event |
| Subscribe to an event and get notified when it changes | `backend/app/notify/`, SSE stream, plus catch-up on reconnect |
| Listeners: sync event updates from Bluesky posts (Host Henry) | An `app.communitymap.listener` record. A post with `#hashtag` becomes an announcement on the event |
| Import from other sources | iCal feeds (`backend/app/ingest/ical.py`, `POST /api/import/ical`) |
| Poor campus WiFi | A service worker caches the app shell and API responses, the app shows a stale-data banner, and responses are gzipped |
| No location stored | The user's position stays in the browser. The server never sees it |

## Docs

- [Architecture + infrastructure diagram](docs/ARCHITECTURE.md)
- [How the work was split](docs/TEAM.md)
- [Design decisions to debate](docs/DECISIONS.md)
- [API and record contracts](docs/CONTRACTS.md) · [Lexicons](lexicons/)
