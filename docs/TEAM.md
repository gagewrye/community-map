# How the work was split

The architect wrote the contracts first. Three engineers (Claude sub-agents) then built against those contracts in parallel. Each one owned a separate set of directories, so nobody blocked anyone else and there were no merge conflicts.

| Phase | Owner | Deliverable |
|---|---|---|
| 0. Contracts | Architect | `lexicons/`, `models.py`, `store/base.py`, `notify/base.py`, `docs/CONTRACTS.md`, repo + CI skeleton |
| 1a. Backend Core | Engineer A | SQLite store, API routers (events, subscriptions, SSE), notifier, expiry, seed data. 41 tests |
| 1b. Ingest | Engineer B | Jetstream client, commit processor + diffs, listeners, handle resolver, iCal import, dev route. 50 tests |
| 1c. Frontend | Engineer C | Vanilla-JS PWA: list/map/detail/compose views, PDS writer, demo writer, subscriptions, service worker. 81 tests |
| 2. Integration | Architect | `main.py`, end-to-end test, SSRF guard, safe defaults, Docker, docs, live checks (browser, SSE, real Jetstream) |

**Why it split this way.** The seams follow the data flow (network → index → API → UI). Each one is a Python `Protocol` or an HTTP contract. Every engineer tested against fakes of the other engineers' interfaces (for example `tests/ingest_fakes.py`), so all three could work at the same time.

**Found during integration and fixed.** Three issues came up:
- **EventView had no `createdAt`.** The Frontend needed it to edit events, so it was added.
- **The iCal import could fetch internal URLs (SSRF).** Ingest flagged this, and `netguard.py` now blocks private hosts.
- **`dev_mode` defaulted to on.** It is now off by default.

**How a human team could map to this split.** The spec lists eight developers. Lead A (backend) could take Core + Ingest with four devs. Lead B (frontend) could take the views + offline/PWA work with four devs. The contracts in Phase 0 are owned by the leads together.
