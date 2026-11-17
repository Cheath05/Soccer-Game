"""Leagues switched off full simulation (world/fast_sim.py; Settings → Simulation). A career
with every league but the Premier League on fast results: their league and cup matches get fast
results with scorers and line-ups, while the Premier League, continental matches and cup ties
with a Premier League club are fully simulated. The user's own league is always fully simulated,
and a career that switches nothing off plays exactly as before. Needs the built world."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from footsim.api.app import create_app
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.world import fast_sim
from footsim.world.career import advance, initialize_career
from footsim.world.context import World, get_world
from footsim.world.meta import read_meta

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
DAYS = 75  # into the league seasons, the first cup rounds and the continental qualifiers


@pytest.fixture(scope="module")
def career(tmp_path_factory: pytest.TempPathFactory) -> tuple[Engine, World]:
    world = get_world()
    path = tmp_path_factory.mktemp("fast") / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    fast = [k for k in fast_sim.selectable(world) if k != "ENG1"]
    with engine.begin() as conn:
        initialize_career(conn, world, None, None, seed=21, fast_leagues=fast)
    with engine.begin() as conn:
        advance(conn, world, max_days=DAYS)
    return engine, world


def _played(engine: Engine) -> list[tuple[str, str, str, str | None, str | None]]:
    """Every played fixture as (competition type, competition key, sim, home's league, away's
    league)."""
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text("""
            SELECT c.type, c.key, f.sim, hl.key, al.key FROM fixture f
            JOIN competition c ON c.id = f.competition_id
            LEFT JOIN club_league_membership hm ON hm.club_id = f.home_club_id
                AND hm.season_id = f.season_id
            LEFT JOIN competition hl ON hl.id = hm.competition_id
            LEFT JOIN club_league_membership am ON am.club_id = f.away_club_id
                AND am.season_id = f.season_id
            LEFT JOIN competition al ON al.id = am.competition_id
            WHERE f.status = 'played'"""))]


def test_only_the_switched_off_matches_are_fast(career: tuple[Engine, World]) -> None:
    engine, _ = career
    played = _played(engine)
    kinds = {(kind, sim) for kind, _, sim, _, _ in played}
    assert ("league", "fast") in kinds and ("league", "quick") in kinds
    assert ("continental", "quick") in kinds and ("cup", "fast") in kinds
    for kind, key, sim, home, away in played:
        if kind == "league":
            assert (sim == "quick") == (key == "ENG1"), key
        elif kind == "continental":
            assert sim == "quick"  # always fully simulated
        elif kind == "cup":
            assert (sim == "quick") == ("ENG1" in (home, away)), (key, home, away)
        elif kind == "college":
            assert sim == "fast"


def test_fast_matches_have_scorers_and_line_ups(career: tuple[Engine, World]) -> None:
    engine, _ = career
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT f.id, f.home_goals + f.away_goals AS goals, f.stats,
                (SELECT COUNT(*) FROM player_match pm WHERE pm.fixture_id = f.id
                 AND pm.started = 1) AS starters,
                (SELECT COALESCE(SUM(minutes), 0) FROM player_match pm
                 WHERE pm.fixture_id = f.id) AS minutes,
                (SELECT COUNT(*) FROM match_event e WHERE e.fixture_id = f.id
                 AND e.type IN ('goal', 'penalty_goal', 'own_goal')) AS goal_events
            FROM fixture f WHERE f.sim = 'fast' AND f.extra_time = 0""")).all()
        assert len(rows) > 1000
        for r in rows:
            assert r.starters == 22 and r.minutes == 22 * 90
            assert r.goal_events == r.goals and r.stats is None
        # Nobody in a fast match is booked or injured.
        assert conn.execute(text("""
            SELECT COUNT(*) FROM match_event e JOIN fixture f ON f.id = e.fixture_id
            WHERE f.sim = 'fast' AND e.type IN ('yellow', 'red', 'injury')""")).scalar_one() == 0
        # The players' season lines count the fast matches: development sees their minutes.
        apps = conn.execute(text("""
            SELECT COUNT(DISTINCT pm.player_id) FROM player_match pm
            JOIN fixture f ON f.id = pm.fixture_id WHERE f.sim = 'fast'""")).scalar_one()
        assert apps > 5000


def test_the_users_league_is_always_fully_simulated(career: tuple[Engine, World]) -> None:
    engine, world = career
    with engine.connect() as conn:
        meta = read_meta(conn)
        assert "ESP1" in fast_sim.effective_fast(conn, meta)
        meta.user_club_id = int(conn.execute(text(
            "SELECT id FROM club WHERE name = 'Real Madrid'")).scalar_one())
        assert "ESP1" not in fast_sim.effective_fast(conn, meta)
        assert "ESP2" in fast_sim.effective_fast(conn, meta)
        with pytest.raises(ValueError, match="unknown leagues"):
            fast_sim.set_fast_leagues(world, meta, ["NOPE"])


def test_kept_team_sheets_are_the_ones_built_now(career: tuple[Engine, World]) -> None:
    engine, world = career
    with engine.begin() as conn:
        meta = read_meta(conn)
        clubs = [int(c) for c in conn.execute(text(
            "SELECT club_id FROM club_league_membership m JOIN competition c "
            "ON c.id = m.competition_id WHERE c.key = 'ESP1' AND m.season_id = 1 LIMIT 3")
        ).scalars()]
        day = meta.current_date
        first = fast_sim._sheets(conn, world, clubs, day)
        again = fast_sim._sheets(conn, world, clubs, day)
        assert all(first[c] is again[c] for c in clubs)  # kept
        # A starter injured: that club's sheet is built again, without him.
        hurt = first[clubs[0]].starters[0].player_id
        conn.execute(text("UPDATE player_state SET injured_until = '2099-01-01' "
                          "WHERE player_id = :p"), {"p": hurt})
        after = fast_sim._sheets(conn, world, clubs, day)
        assert after[clubs[0]] is not first[clubs[0]] and after[clubs[1]] is first[clubs[1]]
        assert hurt not in {sp.player_id for sp in after[clubs[0]].starters}
        conn.rollback()


def test_the_settings_page(tmp_path: Path) -> None:
    client = TestClient(create_app(session=CareerSession(tmp_path / "saves", BASE_WORLD),
                                   frontend=None))
    choices = client.get("/api/world/simulation").json()
    keys = {c["key"] for c in choices}
    assert {"ENG1", "USA1", get_world().defs.college.rules.key} <= keys
    league = next(lg for lg in client.get("/api/world/leagues").json() if lg["key"] == "ENG4")
    club_id = league["clubs"][0]["id"]
    client.post("/api/saves/1/new", json={"club_id": club_id, "manager_name": "Tester",
                                          "fast_leagues": ["ESP1", "ENG4", "NOPE"]})
    start = client.get("/api/settings/simulation").json()
    # Unknown keys are dropped; the user's league is kept in the list but always full.
    assert start == {"fast": ["ENG4", "ESP1"], "user_league": "ENG4"}
    changed = client.put("/api/settings/simulation", json={"fast": ["ITA1", "ITA2"]}).json()
    assert changed["fast"] == ["ITA1", "ITA2"]
    assert client.get("/api/settings/simulation").json()["fast"] == ["ITA1", "ITA2"]
    assert client.put("/api/settings/simulation", json={"fast": ["NOPE"]}).status_code == 422
