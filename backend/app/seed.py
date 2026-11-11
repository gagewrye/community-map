"""Sample UCSD campus events for local development. Run: python -m app.seed"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.models import EVENT_NSID, EventRecord, IndexedEvent, Location
from app.store.base import EventStore

PLACES: dict[str, tuple[str, str, str]] = {
    "price": ("Price Center", "32.8797", "-117.2362"),
    "geisel": ("Geisel Library", "32.8812", "-117.2375"),
    "rimac": ("RIMAC Arena", "32.8853", "-117.2401"),
    "libwalk": ("Library Walk", "32.8795", "-117.2373"),
    "warren": ("Warren Mall", "32.8818", "-117.2343"),
    "sungod": ("Sun God Lawn", "32.8785", "-117.2394"),
    "cse": ("CSE Building", "32.8818", "-117.2335"),
    "revelle": ("Revelle Plaza", "32.8747", "-117.2409"),
    "mandeville": ("Mandeville Auditorium", "32.8780", "-117.2400"),
    "ovt": ("Ocean View Terrace", "32.8833", "-117.2427"),
    "pier": ("Scripps Pier", "32.8665", "-117.2546"),
}

# (rkey, did, handle, name, description, place, start offset h, duration h, tags, group)
SEED: list[tuple[str, str, str, str, str, str, float, float, list[str], str | None]] = [
    (
        "seed01",
        "did:plc:seedtritonfood",
        "tritonfood.bsky.social",
        "Free Pancake Breakfast",
        "Finals fuel! Pancakes and coffee while supplies last.",
        "price",
        -1.0,
        3.0,
        ["food", "free", "social"],
        "Triton Food Collective",
    ),
    (
        "seed02",
        "did:plc:seedgeiselstudy",
        "geisel.bsky.social",
        "Late Night Study Jam",
        "Quiet floors stay open late, with snacks on the 2nd floor.",
        "geisel",
        -2.5,
        3.0,
        ["study", "free", "food"],
        "Geisel Library",
    ),
    (
        "seed03",
        "did:plc:seedtritonclub",
        "tritonclub.bsky.social",
        "Library Walk Club Fair",
        "Meet 100+ student orgs and find your people.",
        "libwalk",
        4.0,
        3.0,
        ["social", "free"],
        "Associated Students",
    ),
    (
        "seed04",
        "did:plc:seedacmucsd",
        "acmucsd.bsky.social",
        "Intro to Rust Workshop",
        "Hands-on workshop, bring a laptop. No experience required.",
        "cse",
        26.0,
        2.0,
        ["tech", "free"],
        "ACM at UCSD",
    ),
    (
        "seed05",
        "did:plc:seedcareer",
        "ucsdcareers.bsky.social",
        "Engineering Career Fair",
        "Recruiters from 60 companies. Bring copies of your resume.",
        "price",
        28.0,
        4.0,
        ["career", "tech"],
        "Career Center",
    ),
    (
        "seed06",
        "did:plc:seedtritonsports",
        "tritons.bsky.social",
        "Tritons vs. Anteaters",
        "Men's basketball rivalry game. Wear blue and gold!",
        "rimac",
        50.0,
        2.5,
        ["sports", "social"],
        "UCSD Athletics",
    ),
    (
        "seed07",
        "did:plc:seedksdt",
        "ksdt.bsky.social",
        "Sun God Lawn Acoustic Sessions",
        "Student bands play acoustic sets at sunset. Blankets welcome.",
        "sungod",
        74.0,
        3.0,
        ["music", "free", "social"],
        "KSDT Radio",
    ),
    (
        "seed08",
        "did:plc:seedwarren",
        "warrencollege.bsky.social",
        "Warren Mall Food Truck Night",
        "Five food trucks, live DJ, and lawn games.",
        "warren",
        98.0,
        3.0,
        ["food", "music", "social"],
        "Warren College Council",
    ),
    (
        "seed09",
        "did:plc:seedtritonclub",
        "tritonclub.bsky.social",
        "Revelle Plaza Open Mic",
        "Poetry, comedy, music: sign up at the table.",
        "revelle",
        122.0,
        2.0,
        ["music", "social", "free"],
        "Associated Students",
    ),
    (
        "seed10",
        "did:plc:seedmandeville",
        "ucsdarts.bsky.social",
        "Winter Orchestra Concert",
        "La Jolla Symphony performs works by Dvorak and Price.",
        "mandeville",
        146.0,
        2.0,
        ["music", "arts"],
        "Department of Music",
    ),
    (
        "seed11",
        "did:plc:seedrecreation",
        "ucsdrec.bsky.social",
        "Sunrise Surf Session",
        "Beginner surf lesson; boards and wetsuits provided.",
        "pier",
        151.0,
        2.0,
        ["sports", "outdoors"],
        "UCSD Recreation",
    ),
    (
        "seed12",
        "did:plc:seedacmucsd",
        "acmucsd.bsky.social",
        "Hack Night at OVT",
        "Build anything. Pizza at 8pm, demos at 11pm.",
        "ovt",
        160.0,
        5.0,
        ["tech", "food", "free"],
        "ACM at UCSD",
    ),
]


def seed_events(now: datetime) -> list[IndexedEvent]:
    out = []
    for rkey, did, handle, name, desc, place, start_h, dur_h, tags, group in SEED:
        loc_name, lat, lng = PLACES[place]
        starts = now + timedelta(hours=start_h)
        record = EventRecord(
            name=name,
            description=desc,
            starts_at=starts,
            ends_at=starts + timedelta(hours=dur_h),
            location=Location(
                name=loc_name, address="9500 Gilman Dr, La Jolla, CA", lat=lat, lng=lng
            ),
            tags=tags,
            group=group,
            created_at=now,
        )
        out.append(
            IndexedEvent(
                uri=f"at://{did}/{EVENT_NSID}/{rkey}",
                cid=f"bafyreiseed{rkey}",
                author_did=did,
                author_handle=handle,
                source="atproto",
                record=record,
                indexed_at=now,
                updated_at=now,
            )
        )
    return out


def seed(store: EventStore, now: datetime) -> int:
    """Upsert the sample events; returns how many were written."""
    return sum(store.upsert_event(ev) != "unchanged" for ev in seed_events(now))


def main() -> None:
    from app.store.sqlite import SqliteStore

    settings = get_settings()
    store = SqliteStore(settings.db_path)
    n = seed(store, datetime.now(UTC))
    print(f"seeded {n} events into {settings.db_path}")


if __name__ == "__main__":
    main()
