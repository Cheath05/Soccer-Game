"""End-to-end API flow on the real base world. Skipped when the world hasn't been built
(it needs the locally downloaded EA FC 27 file, which isn't in the repository)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from footsim.api.app import create_app
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    return TestClient(create_app(session=session, frontend=None))


def test_career_flow(client: TestClient) -> None:
    leagues = client.get("/api/world/leagues").json()
    premier = next(lg for lg in leagues if lg["key"] == "ENG1")
    assert len(premier["clubs"]) == 20
    arsenal = next(c for c in premier["clubs"] if c["name"] == "Arsenal")

    career = client.post("/api/saves/1/new",
                         json={"club_id": arsenal["id"], "manager_name": "Tester"}).json()
    assert career["club"]["name"] == "Arsenal" and career["position"] is None  # pre-season

    stop = client.post("/api/career/advance").json()
    assert stop["stop"] == "match" and stop["fixture_id"]
    assert client.get("/api/career").json()["date"] == stop["date"]

    tactics = client.get("/api/tactics").json()
    assert len(tactics["starters"]) == 11 and len(tactics["bench"]) >= 7
    changed = client.put("/api/tactics", json={
        "formation": "4-4-2", "roles": {}, "lineup": None,
        "instructions": {**tactics["instructions"], "mentality": "attacking"},
    }).json()
    assert changed["formation"] == "4-4-2" and changed["instructions"]["mentality"] == "attacking"

    report = client.post(f"/api/fixtures/{stop['fixture_id']}/play").json()
    assert report["fixture"]["status"] == "played"
    assert len(report["home_lines"]) >= 11 and report["stats"]["home"]["shots"] >= 0

    table = client.get("/api/competitions/ENG1/table").json()
    assert len(table["rows"]) == 20
    assert sum(r["played"] for r in table["rows"]) > 0

    squad = client.get(f"/api/clubs/{arsenal['id']}/squad").json()
    assert len(squad) >= 18
    detail = client.get(f"/api/players/{squad[0]['id']}").json()
    assert detail["own_player"] and detail["potential"]["low"] <= detail["potential"]["high"]

    client.post("/api/saves/save")
    slots = client.get("/api/saves").json()
    assert slots[0]["has_save"] and slots[0]["club"] == "Arsenal"

    after = client.post("/api/career/advance").json()
    assert after["stop"] == "match" and after["date"] > stop["date"]

    reloaded = client.post("/api/saves/1/load").json()
    assert reloaded["date"] == stop["date"]  # unsaved progress is discarded on load


def test_live_match_over_websocket(client: TestClient) -> None:
    leagues = client.get("/api/world/leagues").json()
    club = next(c for lg in leagues if lg["key"] == "ENG2" for c in lg["clubs"])
    client.post("/api/saves/2/new", json={"club_id": club["id"], "manager_name": "Live"})
    stop = client.post("/api/career/advance").json()
    assert stop["stop"] == "match"

    with client.websocket_connect(f"/api/fixtures/{stop['fixture_id']}/live") as ws:
        init = ws.receive_json()
        assert init["type"] == "init" and len(init["lineup"]) == 22 and init["paused"]
        ws.send_json({"type": "speed", "value": 64})
        ws.send_json({"type": "resume"})
        frames = 0
        for _ in range(6):
            msg = ws.receive_json()
            frames += len(msg.get("frames", []))
        assert frames > 100  # 64 ticks per message once running
        ws.send_json({"type": "formation", "key": "4-4-2"})
        ws.send_json({"type": "instruction", "key": "mentality", "value": "attacking"})
        changed = ws.receive_json()
        while changed.get("formation") is None:
            changed = ws.receive_json()
        assert changed["formation"][init["user_team"]] == "4-4-2"
        ws.send_json({"type": "finish"})
        msg = ws.receive_json()
        while msg["type"] != "end":
            msg = ws.receive_json()

    report = client.get(f"/api/fixtures/{stop['fixture_id']}").json()
    assert report["fixture"]["status"] == "played"
    assert report["stats"]["home"]["passes"] > 100
