"""A top league's table shows its European places (access.yaml): the rows' marks by position
and a key that includes the cup winners' places. Lower leagues have none."""

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
    client = TestClient(create_app(session=session, frontend=None))
    premier = next(lg for lg in client.get("/api/world/leagues").json() if lg["key"] == "ENG1")
    client.post("/api/saves/1/new", json={"club_id": premier["clubs"][0]["id"],
                                          "manager_name": "Tester"})
    return client


def test_a_top_league_shows_its_european_places(client: TestClient) -> None:
    table = client.get("/api/competitions/ENG1/table").json()
    assert [(p["competition"], p["stage"], p["how"]) for p in table["europe_places"]] == [
        ("UCL", "league_phase", "1st–4th"),
        ("UEL", "league_phase", "5th"),
        ("UEL", "league_phase", "FA Cup winners"),
        ("UECL", "league_phase", "6th"),
        ("UECL", "qualifying", "7th"),
    ]
    assert table["europe_places"][0]["name"] == "Champions League"
    assert not table["europe_actual"]
    marks = {r["position"]: (r["europe"], r["europe_stage"]) for r in table["rows"]}
    assert all(marks[p] == ("UCL", "league_phase") for p in range(1, 5))
    assert marks[5] == ("UEL", "league_phase") and marks[6] == ("UECL", "league_phase")
    assert marks[7] == ("UECL", "qualifying")
    assert all(marks[p] == (None, None) for p in range(8, 21))


def test_a_smaller_country_and_a_lower_league(client: TestClient) -> None:
    scotland = client.get("/api/competitions/SCO1/table").json()
    assert ("UCL", "qualifying", "1st") in {
        (p["competition"], p["stage"], p["how"]) for p in scotland["europe_places"]}
    lower = client.get("/api/competitions/ENG2/table").json()
    assert lower["europe_places"] == [] and all(r["europe"] is None for r in lower["rows"])
