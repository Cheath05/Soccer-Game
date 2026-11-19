"""FIFA's international windows (W8 I2, world/international/windows.py): a career played
through the first window of 2026-27. The day before it, every national team calls its squad
up; the called-up players are away from their clubs until it ends; every team plays friendlies
(fast results) on its matchdays; Elo moves with the results; and international fixtures don't
count towards the season's rollover. Needs the built world."""

import shutil
from datetime import date, timedelta

import pytest
from sqlalchemy import Engine, text

from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.world.career import advance, initialize_career
from footsim.world.context import World, get_world
from footsim.world.international.common import away_players
from footsim.world.international.windows import FRIENDLY, elo_change, matchdays, windows
from footsim.world.meta import read_meta
from footsim.world.season import season_complete
from footsim.world.squads import load_squad

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


@pytest.fixture(scope="module")
def career(tmp_path_factory: pytest.TempPathFactory) -> tuple[Engine, World, dict[str, object]]:
    """A watch-only career played to the middle of the first window, checked there, and on to
    two days after it."""
    world = get_world()
    path = tmp_path_factory.mktemp("windows") / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, world, None, None, seed=23)
        meta = read_meta(conn)
        first = windows(world, meta)[0]
        start_elo = {r.code: r.elo for r in conn.execute(text(
            "SELECT code, elo FROM national_team"))}
    seen: dict[str, object] = {"window": first, "start_elo": start_elo}
    middle = first.start + timedelta(days=5)
    while True:
        with engine.begin() as conn:
            day = read_meta(conn).current_date
            if day >= middle:
                break
            advance(conn, world, max_days=(middle - day).days)
    with engine.connect() as conn:
        away = away_players(conn, middle)
        seen["away"] = away
        # A called-up player at a club in a league that plays through the window isn't in its
        # line-up while he's away.
        row = conn.execute(text(
            "SELECT k.club_id, k.person_id FROM playing k JOIN national_squad s "
            "ON s.player_id = k.person_id LIMIT 1")).one()
        squad = load_squad(conn, row.club_id, middle)
        seen["available"] = next(p.available for p in squad if p.player_id == row.person_id)
    end = first.end + timedelta(days=2)
    while True:
        with engine.begin() as conn:
            day = read_meta(conn).current_date
            if day >= end:
                break
            advance(conn, world, max_days=(end - day).days)
    return engine, world, seen


def test_squads_are_called_up_for_the_window(career: tuple[Engine, World, dict[str, object]]
                                             ) -> None:
    engine, _, seen = career
    away = seen["away"]
    # 26 each, less the odd injured player a small nation has nobody to replace with.
    assert isinstance(away, set) and 210 * 26 - 30 <= len(away) <= 210 * 26
    assert seen["available"] is False
    with engine.connect() as conn:  # back with their clubs once it's over
        assert away_players(conn, read_meta(conn).current_date) == set()


def test_every_team_plays_its_friendlies(career: tuple[Engine, World, dict[str, object]]
                                         ) -> None:
    engine, world, seen = career
    window = seen["window"]
    days = matchdays(world, window)  # type: ignore[arg-type]
    assert len(days) == 4  # the long September-October window
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT f.date, f.home_club_id, f.away_club_id, f.status, f.sim FROM fixture f "
            "WHERE f.stage = :s"), {"s": FRIENDLY}).all()
        assert {r.status for r in rows} == {"played"} and {r.sim for r in rows} == {"fast"}
        assert sorted({date.fromisoformat(r.date) for r in rows}) == days
        for day in days:  # every team once (with an odd one out at most per pairing group)
            teams = [c for r in rows if r.date == day.isoformat()
                     for c in (r.home_club_id, r.away_club_id)]
            assert len(teams) == len(set(teams)) and len(teams) >= 200
        # Caps: the players took part.
        caps = conn.execute(text(
            "SELECT COUNT(DISTINCT pm.player_id) FROM player_match pm JOIN fixture f "
            "ON f.id = pm.fixture_id WHERE f.stage = :s"), {"s": FRIENDLY}).scalar_one()
        assert caps > 210 * 11
        # International fixtures never hold up the season's rollover.
        assert season_complete(conn, 1) is False  # the leagues still have theirs


def test_elo_moves_with_the_results(career: tuple[Engine, World, dict[str, object]]) -> None:
    engine, world, seen = career
    start = seen["start_elo"]
    assert isinstance(start, dict)
    with engine.connect() as conn:
        now = {r.code: r.elo for r in conn.execute(text("SELECT code, elo FROM national_team"))}
    moved = [code for code in now if abs(now[code] - start[code]) > 0.05]
    assert len(moved) > 150
    # Points only change hands: the total stays (to rounding).
    assert abs(sum(now.values()) - sum(start.values())) < 0.1 * len(now)
    # The formula: an upset moves more than a favourite's win.
    upset = elo_change(world, 1500, 1900, 1, 0, True, "friendly")
    expected = elo_change(world, 1900, 1500, 1, 0, True, "friendly")
    assert upset > 3 * expected > 0
    assert elo_change(world, 1700, 1700, 1, 0, True, "qualifier") == pytest.approx(20.0)
