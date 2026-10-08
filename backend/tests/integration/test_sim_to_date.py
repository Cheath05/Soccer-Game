"""Sim to date on the real base world: the career moves on to the chosen day in the background,
playing the user's matches as Instant would. Skipped when the world hasn't been built (it needs
the locally downloaded EA FC 27 file, which isn't in the repository)."""

import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from match_day import advance_to_match, reject_bids

from footsim.api.app import create_app
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    return TestClient(create_app(session=session, frontend=None))


def _career(client: TestClient) -> dict[str, Any]:
    leagues = client.get("/api/world/leagues").json()
    club = next(c for lg in leagues if lg["key"] == "ENG4" for c in lg["clubs"])
    career: dict[str, Any] = client.post(
        "/api/saves/1/new", json={"club_id": club["id"], "manager_name": "Sim"}).json()
    return career


def _wait(client: TestClient, timeout: float = 240.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        status: dict[str, Any] = client.get("/api/career/sim").json()
        if not status["running"]:
            return status
        assert time.monotonic() < deadline, "the simulation didn't finish"
        time.sleep(0.2)


def test_sim_to_a_date_plays_the_users_matches_on_the_way(client: TestClient) -> None:
    _career(client)
    first = advance_to_match(client)  # to the first match day
    assert first["stop"] == "match"
    until = date.fromisoformat(first["date"]) + timedelta(days=10)

    started = client.post("/api/career/sim", json={"until": until.isoformat()}).json()
    assert started["running"]
    assert client.post("/api/career/advance").status_code == 409  # one thing at a time
    status = _wait(client)
    results = list(status["results"])
    while status["stop"] == "offer":  # a club bid for one of ours: turn it down, sim on
        reject_bids(client)
        client.post("/api/career/sim", json={"until": until.isoformat()})
        status = _wait(client)
        results += status["results"]
    status["results"] = results

    assert status["stop"] == "date" and status["error"] is None
    career = client.get("/api/career").json()
    assert career["date"] == until.isoformat()  # the day itself is left to the user
    played = [r["fixture_id"] for r in status["results"]]
    assert first["fixture_id"] in played and len(played) >= 2
    fixtures = client.get(f"/api/clubs/{career['club']['id']}/fixtures").json()
    assert all(f["status"] == "played" for f in fixtures if f["date"] < until.isoformat())
    assert all(f["status"] == "scheduled" for f in fixtures if f["date"] >= until.isoformat())
    # Autosaved on the way: the autosave is the simulated day.
    assert client.post("/api/saves/1/load?autosave=true").json()["date"] == until.isoformat()


def test_a_sim_can_be_stopped_and_the_game_carries_on(client: TestClient) -> None:
    career = _career(client)
    client.post("/api/career/sim", json={"until": career["season_end"]})
    deadline = time.monotonic() + 120
    while not client.get("/api/career/sim").json()["results"]:
        assert time.monotonic() < deadline, "no match was played"
        status = client.get("/api/career/sim").json()
        if not status["running"] and status["stop"] == "offer":  # a bid: turn it down, sim on
            reject_bids(client)
            client.post("/api/career/sim", json={"until": career["season_end"]})
        time.sleep(0.2)
    client.post("/api/career/sim/stop")

    status = _wait(client)
    assert status["stop"] == "cancelled"
    assert client.get("/api/career").json()["date"] < career["season_end"]
    assert client.post("/api/career/advance").status_code == 200


def test_a_sim_needs_a_date_ahead(client: TestClient) -> None:
    career = _career(client)
    response = client.post("/api/career/sim", json={"until": career["date"]})
    assert response.status_code == 400
    assert client.get("/api/career/sim").json() is None
