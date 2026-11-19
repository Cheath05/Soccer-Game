"""High-school recruiting (W9c) in a watch-only career on the base world: the national class
made at the career's start (sizes, stars, ranks, homes, the same for the same seed), then a
recruiting year from August to the class's close without the matches (the AI programs' offers,
commitments, signing day, every program's roster filled within its money and the roster limit,
the best recruits at the strongest programs), then the class enrolling as freshmen. Needs the
built world."""

import shutil
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Connection, text

from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.world.career import initialize_career
from footsim.world.college import recruiting as rc
from footsim.world.context import get_world
from footsim.world.meta import read_meta

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


@pytest.fixture(scope="module")
def career(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list[str]]:
    """A career at its start (copied aside), then its recruiting year played to the close."""
    folder = tmp_path_factory.mktemp("recruiting")
    path = folder / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    world = get_world()
    with engine.begin() as conn:
        initialize_career(conn, world, None, None, seed=11)
    engine.dispose()
    shutil.copy(path, folder / "start.sqlite")
    engine = open_database(path)
    news: list[str] = []
    with engine.begin() as conn:
        meta = read_meta(conn)
        dates = rc.recruiting_dates(world.defs.college.recruiting, rc.season_start(conn, 1))
        day = meta.current_date
        while day <= dates.close:
            news += rc.progress_recruiting(conn, world, meta, day)
            day += timedelta(days=1)
    engine.dispose()
    return path, news


def _conn(path: Path) -> Connection:
    return open_database(path).connect()


def test_the_class_is_ranked(career: tuple[Path, list[str]]) -> None:
    hs = get_world().defs.college.recruiting
    with _conn(career[0].parent / "start.sqlite") as conn:
        rows = conn.execute(text("SELECT * FROM recruit ORDER BY national_rank")).all()
        assert len(rows) == hs.class_size
        assert {r.class_season for r in rows} == {2}
        assert [r.national_rank for r in rows] == list(range(1, len(rows) + 1))
        grades = [r.grade for r in rows]
        assert grades == sorted(grades, reverse=True)
        stars = Counter(r.stars for r in rows)
        assert stars[5] == 25 and stars[4] == 150 and stars[3] == 600
        assert stars[2] == hs.class_size - 775
        # Position and state ranks count up within each position and state.
        for key in ("position", "state"):
            seen: Counter[str] = Counter()
            for r in rows:
                if getattr(r, key) is None:
                    assert r.state_rank is None
                    continue
                seen[getattr(r, key)] += 1
                assert getattr(r, f"{key}_rank") == seen[getattr(r, key)]
        abroad = sum(r.state is None for r in rows) / len(rows)
        assert 0.10 < abroad < 0.20
        homes = Counter(r.state for r in rows if r.state)
        assert homes.most_common(1)[0][0] in ("CA", "TX")
        assert all(r.status == "open" and r.club_id is None for r in rows)
        assert all(r.potential >= r.overall for r in rows)
        # Better grades mean better players, on average.
        top = [r.overall + r.potential for r in rows[:100]]
        bottom = [r.overall + r.potential for r in rows[-100:]]
        assert sum(top) / 100 > sum(bottom) / 100 + 15
        # Programs have prestige and their players scholarships.
        assert conn.execute(text("SELECT COUNT(*) FROM college_team WHERE prestige IS NULL")
                            ).scalar_one() == 0
        assert conn.execute(text("SELECT MAX(scholarship) FROM college_player")).scalar_one() \
            <= 1.0


def test_the_class_is_the_same_for_the_same_seed(career: tuple[Path, list[str]]) -> None:
    world = get_world()
    engine = open_database(career[0].parent / "start.sqlite")
    with engine.begin() as conn:
        meta = read_meta(conn)
        cols = "first_name, last_name, state, position, overall, potential, grade"
        rc.make_class(conn, world, meta, 50, date(2030, 7, 1))
        first = conn.execute(text(f"SELECT {cols} FROM recruit WHERE class_season = 50 "
                                  "ORDER BY national_rank")).all()
        conn.execute(text("DELETE FROM recruit WHERE class_season = 50"))
        rc.make_class(conn, world, meta, 50, date(2030, 7, 1))
        again = conn.execute(text(f"SELECT {cols} FROM recruit WHERE class_season = 50 "
                                  "ORDER BY national_rank")).all()
        assert first == again
        conn.rollback()
    engine.dispose()


def test_the_ai_programs_recruit_their_classes(career: tuple[Path, list[str]]) -> None:
    path, news = career
    hs = get_world().defs.college.recruiting
    with _conn(path) as conn:
        status = Counter(r[0] for r in conn.execute(text("SELECT status FROM recruit")))
        assert set(status) == {"signed", "gone"}
        assert status["signed"] > 1100
        # Every program back to its target, within the roster limit and its money.
        rows = conn.execute(text("""
            SELECT t.club_id, t.tier,
              (SELECT COUNT(*) FROM college_player cp WHERE cp.club_id = t.club_id
               AND cp.status = 'enrolled' AND cp.class_year < 4) AS back,
              (SELECT COALESCE(SUM(scholarship), 0) FROM college_player cp
               WHERE cp.club_id = t.club_id AND cp.status = 'enrolled' AND cp.class_year < 4)
               AS held,
              (SELECT COUNT(*) FROM recruit r WHERE r.club_id = t.club_id
               AND r.status = 'signed') AS signed,
              (SELECT COALESCE(SUM(share), 0) FROM recruit r WHERE r.club_id = t.club_id
               AND r.status = 'signed') AS money
            FROM college_team t""")).all()
        for r in rows:
            assert hs.programs.roster_target <= r.back + r.signed <= hs.programs.roster_max
            assert r.held + r.money <= hs.programs.funding_by_tier[r.tier] + 1e-6
        # The best recruits go to the strongest programs: every five-star to a tier 1 or 2
        # program, and each tier's class better than the next one's on average.
        five = conn.execute(text("SELECT t.tier FROM recruit r JOIN college_team t "
                                 "ON t.club_id = r.club_id WHERE r.stars = 5")).scalars().all()
        assert len(five) == 25 and max(five) <= 2
        by_tier = dict(conn.execute(text(
            "SELECT t.tier, AVG(r.overall) FROM recruit r JOIN college_team t "
            "ON t.club_id = r.club_id WHERE r.status = 'signed' GROUP BY t.tier")).all())
        assert by_tier[1] > by_tier[3] > by_tier[4] > by_tier[5]
        assert by_tier[2] > by_tier[3]
        # Signings came on and after signing day; offers were made, taken and turned down.
        signing = rc.recruiting_dates(hs, rc.season_start(conn, 1)).signing_day.isoformat()
        assert conn.execute(text("SELECT COUNT(*) FROM recruit WHERE status = 'signed' "
                                 "AND signed_on < :d"), {"d": signing}).scalar_one() == 0
        offers = Counter(r[0] for r in conn.execute(text("SELECT status FROM recruit_offer")))
        assert offers["accepted"] == status["signed"] and offers["declined"] > 500
        assert offers["open"] == 0
        assert conn.execute(text("SELECT COUNT(*) FROM recruit_interest WHERE visited_on "
                                 "IS NOT NULL")).scalar_one() > 0
    assert news == []  # a watch-only career: recruiting is news for a college coach only


def test_the_class_enrolls(career: tuple[Path, list[str]]) -> None:
    path, _news = career
    world = get_world()
    engine = open_database(path)
    with engine.begin() as conn:
        meta = read_meta(conn)
        signed = conn.execute(text("SELECT id, club_id, share, first_name, last_name, "
                                   "potential FROM recruit WHERE status = 'signed' "
                                   "ORDER BY id")).all()
        joined = rc.enroll_class(conn, world, meta, 2, date(2027, 7, 1))
        assert joined == len(signed)
        players = {r.id: r for r in conn.execute(text(
            "SELECT r.id, cp.club_id, cp.class_year, cp.scholarship, cp.entered_season, "
            "p.first_name, p.last_name, pl.pa_hidden, k.kind FROM recruit r "
            "JOIN college_player cp ON cp.player_id = r.player_id "
            "JOIN person p ON p.id = r.player_id JOIN player pl ON pl.person_id = r.player_id "
            "JOIN contract k ON k.person_id = r.player_id AND k.is_active = 1"))}
        assert len(players) == len(signed)
        for s in signed:
            p = players[s.id]
            assert (p.club_id, p.class_year, p.entered_season, p.kind) == (s.club_id, 1, 2,
                                                                            "college")
            assert p.scholarship == pytest.approx(s.share)
            assert (p.first_name, p.last_name) == (s.first_name, s.last_name)
            assert p.pa_hidden >= s.potential
        assert conn.execute(text("SELECT COUNT(*) FROM recruit WHERE status = 'enrolled'")
                            ).scalar_one() == joined
        conn.rollback()
    engine.dispose()
