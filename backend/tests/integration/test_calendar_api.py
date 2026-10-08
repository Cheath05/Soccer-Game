"""The calendar endpoint on the real base world (skipped when it hasn't been built)."""

from datetime import date, timedelta
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


def test_calendar_lists_the_users_fixtures_windows_and_season_bounds(client: TestClient) -> None:
    leagues = client.get("/api/world/leagues").json()
    club = next(c for lg in leagues if lg["key"] == "ENG4" for c in lg["clubs"])
    career: dict[str, Any] = client.post(
        "/api/saves/1/new", json={"club_id": club["id"], "manager_name": "Cal"}).json()
    today = date.fromisoformat(career["date"])
    r = client.get("/api/calendar", params={"from": today.isoformat(),
                                            "to": (today + timedelta(days=120)).isoformat()})
    assert r.status_code == 200
    body = r.json()
    assert body["today"] == career["date"]
    assert body["season_end"] == career["season_end"]
    assert body["fixtures"], "the club has fixtures in the next 120 days"
    assert all(club["id"] in (f["home"]["id"], f["away"]["id"]) for f in body["fixtures"])
    assert all(today.isoformat() <= f["date"] for f in body["fixtures"])
    assert all(today.isoformat() <= d for d in body["window_days"])
    bad = client.get("/api/calendar", params={"from": "2026-09-01", "to": "2026-08-01"})
    assert bad.status_code == 422
