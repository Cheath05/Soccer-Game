"""Club history and past league tables (P16). Skipped when the base world hasn't been built (it
needs the locally downloaded EA FC 27 file, which isn't in the repository)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from footsim.api.app import create_app
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir
from footsim.persistence.schema import competition, league_final

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
GRIMSBY = 218


def test_history_shows_the_season_so_far_then_final_positions(tmp_path: Path) -> None:
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    client = TestClient(create_app(session=session, frontend=None))
    client.post("/api/saves/1/new", json={"club_id": GRIMSBY, "manager_name": "History"})

    history = client.get(f"/api/clubs/{GRIMSBY}/history").json()
    (now,) = history["seasons"]
    assert now["final"] is False and now["position"] is None and now["managed"] is True
    assert now["competition"]["key"] == "ENG4"
    assert [s["current"] for s in client.get("/api/seasons").json()] == [True]

    # As if League Two had finished with Grimsby top and the next club bottom.
    with session.write() as conn:
        eng4 = conn.execute(select(competition.c.id).where(competition.c.key == "ENG4")
                            ).scalar_one()
        other = conn.execute(text(
            "SELECT club_id FROM club_league_membership WHERE competition_id = :c AND "
            "club_id != :g LIMIT 1"), {"c": eng4, "g": GRIMSBY}).scalar_one()
        conn.execute(league_final.insert(), [
            {"season_id": 1, "competition_id": eng4, "club_id": club, "position": pos,
             "played": 46, "won": won, "drawn": 10, "lost": 36 - won, "goals_for": 60,
             "goals_against": 50, "points": 3 * won + 10, "outcome": outcome}
            for club, pos, won, outcome in ((GRIMSBY, 1, 28, "champion"),
                                            (other, 24, 5, "relegated"))])
    history = client.get(f"/api/clubs/{GRIMSBY}/history").json()
    (final,) = history["seasons"]
    assert final["final"] is True and final["position"] == 1 and final["outcome"] == "champion"
    assert history["titles"] == 1 and history["promotions"] == 1  # League Two's champions go up
    assert client.get(f"/api/clubs/{other}/history").json()["relegations"] == 1

    table = client.get("/api/competitions/ENG4/table?season=1").json()
    assert table["final"] is True
    outcomes = {r["club"]["id"]: r["outcome"] for r in table["rows"]}
    assert outcomes[GRIMSBY] == "champion" and outcomes[other] == "relegated"
    assert client.get("/api/clubs/999999/history").status_code == 404
