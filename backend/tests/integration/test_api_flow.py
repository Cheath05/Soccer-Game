"""End-to-end API flow on the real base world. Skipped when the world hasn't been built
(it needs the locally downloaded EA FC 27 file, which isn't in the repository)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from match_day import advance_to_match

from footsim.api.app import create_app
from footsim.api.session import START_STEPS, CareerSession, StartProgress
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

    stop = advance_to_match(client)
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

    after = advance_to_match(client)
    assert after["stop"] == "match" and after["date"] > stop["date"]

    reloaded = client.post("/api/saves/1/load").json()
    assert reloaded["date"] == stop["date"]  # unsaved progress is discarded on load


def test_live_match_over_websocket(client: TestClient) -> None:
    leagues = client.get("/api/world/leagues").json()
    club = next(c for lg in leagues if lg["key"] == "ENG2" for c in lg["clubs"])
    client.post("/api/saves/2/new", json={"club_id": club["id"], "manager_name": "Live"})
    stop = advance_to_match(client)
    assert stop["stop"] == "match"

    with client.websocket_connect(f"/api/fixtures/{stop['fixture_id']}/live") as ws:
        init = ws.receive_json()
        assert init["type"] == "init" and init["protocol"] == 2
        assert len(init["lineup"]) == 22 and init["paused"]
        assert init["clock"]["display"] == "00:00" and init["compression"] == 9
        assert {"ovr", "rating", "energy", "condition"} <= set(init["status"]["players"][0])
        assert all("fit" in b for b in init["status"]["bench"][init["user_team"]])
        ws.send_json({"type": "speed", "value": 64, "cmd_id": 1})
        refused = ws.receive_json()
        while refused["type"] == "frames":  # periodic state while paused
            refused = ws.receive_json()
        assert refused["type"] == "error" and refused["cmd_id"] == 1  # not an offered speed
        ws.send_json({"type": "speed", "value": 8, "cmd_id": 2})
        ws.send_json({"type": "resume", "cmd_id": 3})
        acks: set[int] = set()
        while acks != {2, 3}:
            msg = ws.receive_json()
            if msg["type"] == "ack":
                acks.add(msg["cmd_id"])
        frames, clock = 0, 0.0
        while clock < 30:  # 30 match seconds: about 0.4 real seconds at 8x
            msg = ws.receive_json()
            frames += len(msg.get("frames", []))
            clock = msg["clock"]["elapsed"]
            assert msg["rate"] == 72  # 9 match seconds per real second, times 8
        assert frames > 5
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
        assert msg["clock"]["state"] == "finished"

    report = client.get(f"/api/fixtures/{stop['fixture_id']}").json()
    assert report["fixture"]["status"] == "played"
    assert report["stats"]["home"]["passes"] > 100


def test_starting_a_career_reports_each_stage(tmp_path: Path) -> None:
    """The start page shows how far a new career has got: every stage, in order, then
    nothing once it's done."""
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    client = TestClient(create_app(session=session, frontend=None))
    assert client.get("/api/saves/starting").json() is None
    seen: list[StartProgress | None] = [session.starting]
    started = session._started

    def record(index: int) -> None:
        started(index)
        seen.append(session.starting)

    session._started = record  # type: ignore[method-assign]
    club = client.get("/api/world/leagues").json()[0]["clubs"][0]["id"]
    assert client.post("/api/saves/1/new",
                       json={"club_id": club, "manager_name": "Tester"}).status_code == 200
    assert [p.step for p in seen if p] == list(START_STEPS)
    assert [p.done for p in seen if p] == list(range(len(START_STEPS)))
    assert client.get("/api/saves/starting").json() is None
    # while one is starting, the route says where it has got to
    session.starting = StartProgress.at(2)
    assert client.get("/api/saves/starting").json() == {
        "step": START_STEPS[2], "done": 2, "total": len(START_STEPS)}


def test_deleting_a_save(client: TestClient) -> None:
    club = client.get("/api/world/leagues").json()[0]["clubs"][0]["id"]
    for slot in (1, 2):
        client.post(f"/api/saves/{slot}/new", json={"club_id": club, "manager_name": "Tester"})
    # slot 2 is being played: deleting it closes it
    slots = client.delete("/api/saves/2").json()
    assert [s["has_save"] for s in slots] == [True, False, False]
    assert client.get("/api/career").status_code == 409
    slots = client.delete("/api/saves/1").json()
    assert not any(s["has_save"] or s["has_autosave"] for s in slots)
    assert client.delete("/api/saves/9").status_code == 404
