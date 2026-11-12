# Design decisions to debate

These are the choices made in this prototype that go beyond the ADRs, with the main argument against each.

1. **The backend is a read-only AppView. Clients write to their own PDS.**
   *For:* the data really belongs to users, we hold no credentials, and the design follows AT Protocol conventions.
   *Against:* new events take Relay → Jetstream time (usually about a second) to show up, and we can't moderate them before they are published.

2. **Subscriptions are anonymous and server-side (a random `subscriberId` per browser), not records in the PDS.**
   *For:* subscriptions stay private (PDS records are public), and no login is needed to follow an event.
   *Against:* they don't follow you across devices, and they can't be moved to another AppView.

3. **SSE instead of Web Push.**
   *For:* no keys and no push service. It works on every browser, and missed notifications are caught up on reconnect.
   *Against:* nothing arrives while the tab is closed. Web Push (VAPID) is the next step for the Larry persona.

4. **SQLite in a single container.**
   *For:* free, nothing to operate, fast enough for one campus. The index can be rebuilt by replaying Jetstream.
   *Against:* no horizontal scaling. `EventStore` is a Protocol, so moving to Postgres means writing one new file.

5. **Expiry deletes the event from the index, not from the PDS.**
   *For:* we can't delete user data, and it shouldn't be ours to delete.
   *Against:* expired records stay on the network, and another AppView might still show them.

6. **Listeners match a hashtag on the host's own posts.**
   *For:* simple, and it can't be spoofed (the listener has to be owned by the same DID as the event).
   *Against:* the post text becomes an announcement but doesn't change the event's fields. Structured sync, such as "post says the room changed", would need parsing or an LLM.

7. **"Near me" is computed in the browser.**
   *For:* we never see or store anyone's location, which addresses the location risk in §5.3.
   *Against:* we can't do a server-side radius query, so the client re-sorts only the pages it has already loaded.

8. **Lat/lng are optional strings in the lexicon.**
   *For:* lexicons have no float type, and the list-first ADR means coordinates aren't required.
   *Against:* events without coordinates don't appear on the map. Changing a lexicon later is costly, so this is worth deciding now.

## Known gaps

- **Login uses Bluesky app passwords, not OAuth.** OAuth is the right long-term choice but needs a hosted client-metadata document.
- **There is no moderation or trust score yet.** We rely on Bluesky's account-level moderation.
- **The iCal guard can be bypassed by DNS rebinding.** Pin the resolved IP before production.
- **Bluesky login and the map tab aren't covered by the Playwright tests.** The tests use demo mode and simulate Bluesky posts with dev commits, so real login and the map are still unverified.
