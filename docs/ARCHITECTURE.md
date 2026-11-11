# Architecture

## Infrastructure

```mermaid
flowchart LR
  subgraph Browser["Student's browser (vanilla JS PWA)"]
    UI["List / Map / Compose views"]
    SW["Service worker<br/>offline cache"]
    GEO["Geolocation<br/>(never leaves device)"]
  end

  subgraph ATP["AT Protocol network"]
    PDS[("User's PDS<br/>bsky.social or self-hosted")]
    RELAY["Relay"]
    JS["Jetstream<br/>(JSON firehose)"]
    PLC["plc.directory<br/>DID → handle"]
  end

  subgraph Host["Our container (Fly / Render free tier)"]
    API["FastAPI AppView<br/>/api/*  +  static frontend"]
    ING["Ingest<br/>Jetstream client · CommitProcessor"]
    ICAL["iCal poller"]
    EXP["Expiry sweeper"]
    NOTIF["Notifier<br/>SSE fan-out"]
    DB[("SQLite index<br/>events · tags · subs · notifications")]
  end

  EXT["External calendars (.ics)"]

  UI -- "createRecord / putRecord<br/>(event, listener)" --> PDS
  PDS --> RELAY --> JS
  JS -- "WebSocket: event + listener records<br/>posts only from listener DIDs" --> ING
  ING --> DB
  ING -.-> PLC
  ICAL -- "HTTP poll" --> EXT
  ICAL --> DB
  EXP --> DB
  ING & ICAL & EXP --> NOTIF --> DB
  UI -- "GET /api/events, /tags, /groups" --> API --> DB
  NOTIF -- "SSE /api/notifications/stream" --> UI
  SW -.caches.- API
```

## How data moves

1. **Write.** The host's browser writes an `app.communitymap.event` record straight to their PDS. Our server never holds their credentials.
2. **Index.** The PDS passes the record to the relay and then to Jetstream. `JetstreamClient` sends it to `CommitProcessor`, which validates it against the lexicon and upserts it into SQLite. A cursor is saved so a restart picks up where it left off.
3. **Notify.** If an update changes something people can see (time, place, name), the processor builds a readable diff and sends it to everyone subscribed. They get it on the SSE stream, and it is also saved so they can catch up after going offline.
4. **Listeners (Host Henry).** A host can attach a listener record (event + hashtag) to an event. When that host posts on Bluesky with the hashtag, the post becomes an announcement on the event. We only subscribe to posts from accounts that have a listener, never the full firehose.
5. **Expire.** Each sweep tells subscribers that the event has ended, then deletes it from the index. The record stays on the user's PDS, since that data belongs to them.

## Code layout (each box is one team's area)

```
lexicons/            record schemas (the public contract on the network)
backend/app/
  models.py          shared Pydantic models (contract)
  store/base.py      EventStore Protocol (contract) → sqlite.py
  notify/base.py     Notifier Protocol (contract)   → service.py (SSE)
  ingest/            jetstream.py · processor.py · ical.py · handles.py · netguard.py
  api/               meta · events · subscriptions · imports · dev
  expiry.py seed.py views.py
  main.py            composition root (the only file that knows concrete classes)
frontend/src/
  api.js cache.js store.js filters.js geo.js subscriptions.js
  atproto.js devWriter.js   (same interface, so writers can be swapped)
  views/             listView · mapView · detailView · composeView · filterBar · loginView
  app.js             wiring
```

Modules only depend on the interfaces. Swapping SQLite for Postgres, Jetstream for another feed, or Leaflet tiles for Overture only touches one file plus `main.py`.
