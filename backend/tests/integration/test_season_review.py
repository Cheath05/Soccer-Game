"""The season summary on the real base world, after a real rollover (promotion, relegation,
retirements and the youth intake, then the next season's record of every player). The season
itself isn't played: the league tables are written as if it had been, which is all the rollover
reads. Skipped when the world hasn't been built (it needs the locally downloaded EA FC 27
file, which isn't in the repository)."""

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from footsim.api.app import create_app
from footsim.api.season_review import season_final
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir
from footsim.persistence.schema import league_final
from footsim.world.context import get_world
from footsim.world.meta import read_meta, write_meta
from footsim.world.season import active_leagues, develop_players, members, rollover

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
GRIMSBY = 218


def test_the_summary_after_a_rollover(tmp_path: Path) -> None:
    world = get_world()
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    session.new_career(1, GRIMSBY, "Review")
    leagues = {}
    with session.write() as conn:
        meta = read_meta(conn)
        for month in (8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6):  # the season's monthly development
            develop_players(conn, world, meta, date(2026 if month > 6 else 2027, month, 1), 1 / 12)
        # Every league's table, in club order: the best-placed play-off entrant wins the play-offs.
        for active in active_leagues(conn, world):
            clubs = members(conn, 1, active.competition_id)
            entrants = sorted(r for p in active.league.playoffs for r in p.entrant_ranks())
            leagues[active.league.key] = len(clubs)
            conn.execute(league_final.insert(), [
                {"season_id": 1, "competition_id": active.competition_id, "club_id": c,
                 "position": n, "played": 0, "won": 0, "drawn": 0, "lost": 0, "goals_for": 0,
                 "goals_against": 0, "points": 0,
                 "outcome": "champion" if n == 1 else
                 "playoff_winner" if entrants and n == entrants[0] else None}
                for n, c in enumerate(clubs, start=1)])
        news = rollover(conn, world, meta)
        write_meta(conn, meta)
    with session.read() as conn:
        final = season_final(conn, world, GRIMSBY, news)
        recorded = conn.execute(text(
            "SELECT season_id, COUNT(*) FROM player_season_overall GROUP BY season_id")).all()
        playing: int = conn.execute(text(
            "SELECT COUNT(*) FROM player WHERE retired_on IS NULL")).scalar_one()
    assert final is not None and final.review is not None
    review = final.review
    assert (review.season, review.next_season) == ("2026-27", "2027-28")
    assert {h.key for h in review.honours if h.kind == "league"} == set(leagues)
    assert review.honours[0].nation == "ENG" and review.honours[0].tier == 1
    assert review.promoted and review.relegated
    assert {m.club.id for m in review.promoted}.isdisjoint(m.club.id for m in review.relegated)
    assert all(m.from_league != m.to_league for m in review.promoted + review.relegated)
    assert review.youth and review.retired  # the user's academy intake; the notable retirements
    assert review.development_recorded and review.development_since is None
    assert review.development and all(d.change == d.after - d.before != 0
                                      for d in review.development)
    assert [d.change for d in review.development] == sorted(
        (d.change for d in review.development), reverse=True)  # best improvement first
    # The season's record was taken at the start, and the next one now, after the turnover.
    assert [r[0] for r in recorded] == [1, 2] and recorded[1][1] == playing
    # Of dozens of messages, only the first-round cup draws and the user's contracts running
    # out (W4-7) are news the sections don't cover.
    assert len(news) > 20 and final.news and all(
        " draw: " in m or "contract runs out" in m or "another year" in m for m in final.news)


def test_the_api_serves_a_players_seasons_and_fixtures_by_season(tmp_path: Path) -> None:
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    client = TestClient(create_app(session=session, frontend=None))
    client.post("/api/saves/1/new", json={"club_id": GRIMSBY, "manager_name": "Api"})
    squad = client.get(f"/api/clubs/{GRIMSBY}/squad").json()

    assert client.get(f"/api/players/{squad[0]['id']}/seasons").json() == []  # no match yet
    assert client.get("/api/players/99999999/seasons").status_code == 404
    now = client.get(f"/api/clubs/{GRIMSBY}/fixtures").json()
    assert now and client.get(f"/api/clubs/{GRIMSBY}/fixtures?season=1").json() == now
    assert client.get(f"/api/clubs/{GRIMSBY}/fixtures?season=2").json() == []
    assert [(s["current"], s["finished"]) for s in client.get("/api/seasons").json()] == [
        (True, False)]
    assert client.get("/api/competitions/ENG4/table").json()["started"] is False
