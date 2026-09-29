"""A live match belongs to the career that started it: it can't be played twice, and it
can't write into another save that was loaded in the meantime. Needs the built world."""

from pathlib import Path
from typing import Any

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


def _start(client: TestClient, slot: int, league: str = "ENG2", pick: int = 0) -> int:
    leagues = client.get("/api/world/leagues").json()
    club = [c for lg in leagues if lg["key"] == league for c in lg["clubs"]][pick]
    client.post(f"/api/saves/{slot}/new", json={"club_id": club["id"], "manager_name": "T"})
    stop = client.post("/api/career/advance").json()
    assert stop["stop"] == "match"
    fixture_id: int = stop["fixture_id"]
    return fixture_id


def _until(ws: Any, kind: str) -> dict[str, Any]:
    while True:
        msg: dict[str, Any] = ws.receive_json()
        if msg["type"] == kind:
            return msg


def test_instant_result_refused_while_playing_live(client: TestClient) -> None:
    fixture = _start(client, 1)
    with client.websocket_connect(f"/api/fixtures/{fixture}/live") as ws:
        assert ws.receive_json()["type"] == "init"
        response = client.post(f"/api/fixtures/{fixture}/play")
        assert response.status_code == 409
        ws.send_json({"type": "finish"})
        _until(ws, "end")
    report = client.get(f"/api/fixtures/{fixture}").json()
    assert report["fixture"]["status"] == "played"
    assert len(report["events"]) == len({(e["minute"], e["type"], e["player"])
                                         for e in report["events"]})  # recorded once


def test_live_match_is_autosaved(client: TestClient) -> None:
    fixture = _start(client, 1)
    with client.websocket_connect(f"/api/fixtures/{fixture}/live") as ws:
        ws.receive_json()
        ws.send_json({"type": "finish"})
        _until(ws, "end")
    client.post("/api/saves/1/load?autosave=true")
    assert client.get(f"/api/fixtures/{fixture}").json()["fixture"]["status"] == "played"


def test_loading_another_career_abandons_the_live_match(client: TestClient) -> None:
    fixture = _start(client, 1)
    with client.websocket_connect(f"/api/fixtures/{fixture}/live") as ws:
        ws.receive_json()
        client.post("/api/saves/2/new", json={"club_id": client.get(
            "/api/world/leagues").json()[0]["clubs"][0]["id"], "manager_name": "Other"})
        ws.send_json({"type": "finish"})
        error = _until(ws, "error")
        assert "Another career" in error["message"]
    # Slot 1 never saw the result, and slot 2's fixture with the same id wasn't touched.
    assert client.get(f"/api/fixtures/{fixture}").json()["fixture"]["status"] == "scheduled"
    client.post("/api/saves/1/load?autosave=true")
    assert client.get(f"/api/fixtures/{fixture}").json()["fixture"]["status"] == "scheduled"
