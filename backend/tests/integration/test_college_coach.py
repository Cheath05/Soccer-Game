"""A college coach's career (W9c): a new career at an NCAA program, on the base world. The
program is the user's club once the college world is made, with no board or finances; its
matches stop Continue and, as the NCAA is the coach's league, it is fully simulated even when set
to fast results; the career and
squad say what a college coach needs (conference, tier, class, scholarship); players leave the
program as free agents, and the program can't sign professionals. Needs the built world."""

import shutil
from pathlib import Path

import pytest
from sqlalchemy import Engine, select, text

from footsim.api import queries
from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.persistence.schema import club_finance, fixture
from footsim.world.career import advance, initialize_career, play_user_instant
from footsim.world.college.common import is_college_club
from footsim.world.context import World, get_world
from footsim.world.fast_sim import user_league
from footsim.world.meta import read_meta
from footsim.world.transfers import Move, MoveRefused, validate_move

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
PROGRAM = "Indiana Hoosiers"


@pytest.fixture(scope="module")
def career(tmp_path_factory: pytest.TempPathFactory) -> tuple[Engine, World]:
    path: Path = tmp_path_factory.mktemp("coach") / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    world = get_world()
    with engine.begin() as conn:
        initialize_career(conn, world, None, "Coach", seed=5, fast_leagues=["NCAA", "ENG1"],
                          college_program=PROGRAM)
    return engine, world


def test_the_career_is_at_the_program(career: tuple[Engine, World]) -> None:
    engine, world = career
    with engine.connect() as conn:
        meta = read_meta(conn)
        assert meta.user_club_id is not None and is_college_club(conn, meta.user_club_id)
        assert not meta.board_enabled
        assert user_league(conn, meta) == "NCAA"
        out = queries.career(conn, world, 1)
        assert out.club.name == PROGRAM and out.competition is None
        assert out.college is not None and out.college.conference == "B1G"
        assert out.college.tier == 1 and 60 < out.college.prestige < 100
        assert out.next_fixture is not None
        assert conn.execute(select(club_finance).where(
            club_finance.c.club_id == meta.user_club_id)).first() is None
        squad = queries.squad(conn, world, meta.user_club_id)
        assert 26 <= len(squad) <= 28
        assert all(p.college is not None for p in squad)
        assert {p.college.class_year for p in squad if p.college} == {"Fr", "So", "Jr", "Sr"}
        assert all(p.wage_weekly_eur == 0 for p in squad)
        assert sum(p.college.scholarship for p in squad if p.college) > 5


def test_the_programs_matches_are_the_users(career: tuple[Engine, World]) -> None:
    engine, world = career
    with engine.begin() as conn:
        result = advance(conn, world)
        # Recruiting's offers opening (1 August) is one of a college coach's set days.
        assert result.stop == "stop_day" and result.date.isoformat().endswith("-08-02")
        result = advance(conn, world)
        assert result.stop == "match" and result.fixture_id is not None
        meta = read_meta(conn)
        fx = conn.execute(select(fixture).where(fixture.c.id == result.fixture_id)).one()
        assert meta.user_club_id in (fx.home_club_id, fx.away_club_id)
        assert fx.stage == "college"
        play_user_instant(conn, world, meta, fx, meta.current_date)
        played = conn.execute(select(fixture.c.sim).where(fixture.c.id == fx.id)).scalar_one()
        assert played == "instant"  # fully simulated, though the NCAA is on fast results
        # The NCAA is the coach's league, so all of it is fully simulated, as a professional
        # manager's league is.
        assert conn.execute(text("SELECT COUNT(*) FROM fixture WHERE stage = 'college' AND "
                                 "sim = 'fast'")).scalar_one() == 0
        assert conn.execute(text("SELECT COUNT(*) FROM fixture WHERE status = 'played' AND "
                                 "stage = 'college'")).scalar_one() > 50


def test_players_leave_as_free_agents_and_pros_cant_join(career: tuple[Engine, World]) -> None:
    engine, world = career
    with engine.begin() as conn:
        meta = read_meta(conn)
        assert meta.user_club_id is not None
        squad = queries.squad(conn, world, meta.user_club_id)
        leaving = next(p for p in squad if p.position != "GK")
        queries.release_player(conn, world, leaving.id, meta.current_date)
        status = conn.execute(text("SELECT status FROM college_player WHERE player_id = :p"),
                              {"p": leaving.id}).scalar_one()
        assert status == "undrafted"
        assert leaving.id not in {p.id for p in queries.squad(conn, world, meta.user_club_id)}
        pro = conn.execute(text("SELECT person_id FROM contract WHERE kind = 'player' AND "
                                "is_active = 1 ORDER BY person_id LIMIT 1")).scalar_one()
        with pytest.raises(MoveRefused, match="high-school recruits"):
            validate_move(conn, world, meta, Move(int(pro), meta.user_club_id, by_user=True),
                          meta.current_date)
        conn.rollback()


def test_the_assistant_trains_positions(career: tuple[Engine, World]) -> None:
    """Settings → Position training (20 Nov): each of the user's players not learning a
    position starts on the familiar, not natural, position he knows best; once only."""
    from footsim.world.training import auto_train

    engine, world = career
    natural = world.defs.development.position_training.natural
    with engine.begin() as conn:
        meta = read_meta(conn)
        started = auto_train(conn, world, meta, meta.current_date)
        assert started > 0
        assert auto_train(conn, world, meta, meta.current_date) == 0  # nobody twice
        rows = conn.execute(text(
            "SELECT t.player_id, t.position, pp.familiarity, (SELECT MAX(familiarity) FROM "
            "player_position o WHERE o.player_id = t.player_id AND o.familiarity < :n) AS best "
            "FROM position_training t JOIN player_position pp ON pp.player_id = t.player_id "
            "AND pp.position = t.position"), {"n": natural}).all()
        assert len(rows) == started
        assert all(0 < r.familiarity < natural and r.familiarity == r.best for r in rows)
        conn.rollback()


def test_the_hall_of_fame_lists_who_played(career: tuple[Engine, World]) -> None:
    """The Hall of fame page (20 Nov): everyone who has played for the user's club, with his
    record there; the greats need hall_of_fame's appearances first."""
    from contextlib import contextmanager
    from typing import Any

    from footsim.api.hall_of_fame import hall_of_fame

    engine, world = career

    class _Session:
        @contextmanager
        def read(self) -> Any:
            with engine.connect() as conn:
                yield conn

    with engine.connect() as conn:
        user = read_meta(conn).user_club_id
        played = conn.execute(text("SELECT COUNT(DISTINCT player_id) FROM player_match "
                                   "WHERE club_id = :c"), {"c": user}).scalar_one()
    out = hall_of_fame(_Session())  # type: ignore[arg-type]
    assert out.club.id == user and "appearances" in out.rule
    assert len(out.players) == played
    rules = world.defs.lifecycle.hall_of_fame
    assert all(p.appearances >= rules.min_apps for p in out.players if p.hall_of_fame)
    assert all(p.now == "with_you" for p in out.players)  # nobody has left yet


def test_a_game_day_visit_moves_with_the_result(career: tuple[Engine, World]) -> None:
    """Game-day visits (20 Nov): an invited recruit gains the visit's boost times the result's
    factor once the game is played; one invitation a recruit, and only to home games."""
    from footsim.world.college import visits

    engine, world = career
    rules = world.defs.college.recruiting.programs
    with engine.begin() as conn:
        meta = read_meta(conn)
        games = visits.home_games(conn, world, meta)
        assert games and all(g.date >= meta.current_date for g in games)
        rid = int(conn.execute(text(
            "SELECT id FROM recruit WHERE class_season = :c AND status = 'open' "
            "ORDER BY national_rank LIMIT 1 OFFSET 400"), {"c": meta.season_id + 1}).scalar_one())
        visits.invite(conn, world, meta, rid, games[0].fixture_id)
        assert read_meta(conn).gameday_visits == {rid: games[0].fixture_id}
        away = conn.execute(select(fixture.c.id).where(
            fixture.c.away_club_id == meta.user_club_id, fixture.c.status == "scheduled")
            .limit(1)).scalar_one()
        with pytest.raises(visits.VisitRefused):
            visits.invite(conn, world, read_meta(conn), rid, int(away))
        before = float(conn.execute(text(
            "SELECT interest FROM recruit_interest WHERE recruit_id = :r AND club_id = :c"),
            {"r": rid, "c": meta.user_club_id}).scalar_one())
        conn.execute(text("UPDATE fixture SET status = 'played', home_goals = 3, away_goals = 0 "
                          "WHERE id = :f"), {"f": games[0].fixture_id})
        news = visits.settle(conn, world, read_meta(conn), games[0].date)
        after = conn.execute(text(
            "SELECT interest, visited_on FROM recruit_interest WHERE recruit_id = :r AND "
            "club_id = :c"), {"r": rid, "c": meta.user_club_id}).one()
        assert after.visited_on == games[0].date.isoformat() and len(news) == 1
        assert float(after.interest) == pytest.approx(
            min(100.0, before + rules.visit_boost * rules.gameday_visit.big_win))
        assert read_meta(conn).gameday_visits == {}
        assert visits.factor(world, 1, 0) > visits.factor(world, 1, 1) > visits.factor(world, 0, 1)
        conn.rollback()
