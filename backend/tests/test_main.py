"""Integration test: full app wired by main.create_app, dev commit -> feed -> notification."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def commit(op: str, record: dict | None = None) -> dict:
    c = {"operation": op, "collection": "app.communitymap.event", "rkey": "3kabc", "cid": op}
    if record:
        c["record"] = record
    return {"did": "did:plc:host", "time_us": 1, "kind": "commit", "commit": c}


RECORD = {
    "name": "Taco Night",
    "startsAt": "2099-01-01T18:00:00Z",
    "endsAt": "2099-01-01T20:00:00Z",
    "location": {"name": "Price Center"},
    "tags": ["food"],
    "createdAt": "2098-12-01T00:00:00Z",
}


def test_end_to_end(tmp_path):
    settings = Settings(db_path=str(tmp_path / "t.db"), dev_mode=True, frontend_dir="../frontend")
    with TestClient(create_app(settings, background=False)) as client:
        assert client.get("/api/health").json()["ok"] is True
        assert client.post("/api/dev/records", json=commit("create", RECORD)).status_code == 200

        events = client.get("/api/events", params={"tag": "food"}).json()["events"]
        assert [e["name"] for e in events] == ["Taco Night"]
        uri = events[0]["uri"]

        sub = {"subscriberId": "tester-123", "eventUri": uri}
        assert client.post("/api/subscriptions", json=sub).status_code == 204

        moved = {**RECORD, "location": {"name": "Sun God Lawn"}}
        client.post("/api/dev/records", json=commit("update", moved))
        notes = client.get("/api/notifications", params={"subscriberId": "tester-123"}).json()
        assert notes[0]["kind"] == "updated"
        assert "Sun God Lawn" in notes[0]["message"]

        assert client.get("/").status_code == 200  # frontend served


def test_dev_route_disabled_by_default(tmp_path):
    settings = Settings(db_path=str(tmp_path / "t.db"))
    with TestClient(create_app(settings, background=False)) as client:
        assert client.post("/api/dev/records", json=commit("create", RECORD)).status_code == 404
