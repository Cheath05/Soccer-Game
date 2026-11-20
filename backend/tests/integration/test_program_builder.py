"""The NCAA program builder mode (W9d) on the base world: a builder career's programs have money
and facilities from the start, their season's opening adds up, recruiting spends the class
budget, upgrades are paid for and wait for the season, the budget and upgrades are refused
beyond the money, training speeds growth, home games sell tickets with a crowd that scales home
advantage, and AI programs build. A classic career has none of it. Needs the built world."""

import shutil
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Engine, select, text

from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.persistence.schema import fixture
from footsim.world.career import advance, initialize_career, play_user_instant
from footsim.world.college import program as pg
from footsim.world.college.recruiting import load_programs
from footsim.world.context import World, get_world
from footsim.world.meta import read_meta

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
PROGRAM = "Wake Forest Demon Deacons"


def _career(folder: Path, mode: str) -> Engine:
    path = folder / f"{mode}.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, get_world(), None, "Coach", seed=4,
                          fast_leagues=list(get_world().defs.leagues),
                          college_program=PROGRAM, college_mode=mode)
    return engine


@pytest.fixture(scope="module")
def builder(tmp_path_factory: pytest.TempPathFactory) -> tuple[Engine, World]:
    return _career(tmp_path_factory.mktemp("builder"), "builder"), get_world()


def test_a_classic_career_has_none_of_it(tmp_path: Path) -> None:
    engine = _career(tmp_path, "classic")
    with engine.connect() as conn:
        assert not pg.is_on(conn) and read_meta(conn).college_mode == "classic"
        assert pg.growth_factors(conn, get_world()) == {}


def test_the_programs_start_with_money_and_facilities(builder: tuple[Engine, World]) -> None:
    engine, world = builder
    cfg = pg.rules(world)
    with engine.connect() as conn:
        meta = read_meta(conn)
        assert meta.college_mode == "builder" and pg.is_on(conn)
        rows = conn.execute(text(
            "SELECT p.club_id, t.tier, p.balance_cents, p.class_budget FROM college_program p "
            "JOIN college_team t ON t.club_id = p.club_id")).all()
        assert len(rows) == 213
        built = pg.facilities(conn)
        for r in rows:
            levels = {k: f.level for k, f in built[int(r.club_id)].items()}
            assert levels == {k: cfg.facilities.start_level[k][int(r.tier)]
                              for k in ("training", "stadium")}
            # The opening added up: the starting balance plus the ledger.
            posted = conn.execute(text("SELECT COALESCE(SUM(amount_cents), 0) FROM "
                                       "college_ledger WHERE club_id = :c"),
                                  {"c": r.club_id}).scalar_one()
            assert r.balance_cents == pg.cents(world, cfg.starting_balance[int(r.tier)]) + posted
            assert r.balance_cents > 0 and r.class_budget >= 0
        # Recruiting's money is the returning players' and the class budget.
        programs = load_programs(conn, world, meta.season_id + 1)
        user = programs[meta.user_club_id or 0]
        budget = pg.class_budgets(conn)[user.club_id]
        assert user.funding == pytest.approx(user.returning_money + budget)
        # Training speeds growth, more at a higher level.
        factors = pg.growth_factors(conn, world)
        assert factors and max(factors.values()) > min(factors.values()) >= 1.0


def test_the_budget_and_upgrades_have_limits(builder: tuple[Engine, World]) -> None:
    engine, world = builder
    with engine.begin() as conn:
        meta = read_meta(conn)
        user = meta.user_club_id or 0
        most = pg.affordable_class(conn, world, user, meta.season_id)
        with pytest.raises(pg.ProgramError, match="afford"):
            pg.set_class_budget(conn, world, meta, user, most + 5)
        pg.set_class_budget(conn, world, meta, user, 2.0)
        assert pg.class_budgets(conn)[user] == 2.0
        stadium = pg.facilities(conn)[user]["stadium"]
        conn.execute(text("UPDATE college_program SET balance_cents = 100 WHERE club_id = :c"),
                     {"c": user})
        with pytest.raises(pg.ProgramError, match="money"):
            pg.upgrade(conn, world, meta, user, "stadium", meta.current_date)
        conn.execute(text("UPDATE college_program SET balance_cents = 10000000000 "
                          "WHERE club_id = :c"), {"c": user})
        ready = pg.upgrade(conn, world, meta, user, "stadium", meta.current_date)
        assert ready == meta.season_id + 1  # ordered in July: ready next season
        after = pg.facilities(conn)[user]["stadium"]
        assert (after.level, after.building_to) == (stadium.level, stadium.level + 1)
        with pytest.raises(pg.ProgramError, match="under way"):
            pg.upgrade(conn, world, meta, user, "stadium", meta.current_date)
        assert pg.ready_season(world, conn, meta.season_id, date(2027, 4, 1)) == \
            meta.season_id + 2
        # The next season's opening finishes the work.
        pg.open_season(conn, world, meta, meta.season_id + 1, date(2027, 7, 1))
        assert pg.facilities(conn)[user]["stadium"].level == stadium.level + 1
        conn.rollback()


def test_home_games_sell_tickets_and_the_crowd_scales(builder: tuple[Engine, World]) -> None:
    engine, world = builder
    with engine.begin() as conn:
        result = advance(conn, world)
        meta = read_meta(conn)
        fx = conn.execute(select(fixture).where(fixture.c.id == result.fixture_id)).one()
        seen = pg.crowd(conn, world, fx)
        if not fx.neutral:
            assert seen is not None and 0 < seen.attendance <= seen.capacity
            assert seen == pg.crowd(conn, world, fx)  # from the state before the game
            assert pg.rules(world).crowd.min_scale <= pg.crowd_scale(world, seen) <= 1.0
        play_user_instant(conn, world, meta, fx, meta.current_date)
        pg.progress_program(conn, world, meta, meta.current_date)
        home = conn.execute(select(fixture).where(
            fixture.c.date == meta.current_date.isoformat(), fixture.c.stage == "college",
            fixture.c.status == "played")).all()
        assert home and all(r.attendance for r in home if not r.neutral)
        tickets = conn.execute(text("SELECT COUNT(*) FROM college_ledger WHERE kind = 'tickets' "
                                    "AND date = :d"), {"d": meta.current_date.isoformat()}
                               ).scalar_one()
        assert tickets == sum(1 for r in home if not r.neutral)
        # A full big stadium gives the calibrated effect, an empty small one less.
        assert pg.crowd_scale(world, pg.Crowd(12000, 12000)) == pytest.approx(1.0)
        assert pg.crowd_scale(world, pg.Crowd(100, 1000)) < 0.7
        assert pg.crowd_scale(world, None) == 1.0  # professional games


def test_ai_programs_build(builder: tuple[Engine, World]) -> None:
    engine, world = builder
    with engine.begin() as conn:
        meta = read_meta(conn)
        before = sum(1 for kinds in pg.facilities(conn).values() for f in kinds.values()
                     if f.building_to is not None)
        conn.execute(text("UPDATE college_program SET balance_cents = balance_cents + 500000000"))
        pg.progress_program(conn, world, meta, date(meta.current_date.year, 10, 1))
        after = pg.facilities(conn)
        building = sum(1 for kinds in after.values() for f in kinds.values()
                       if f.building_to is not None)
        assert building > before + 50
        user = after[meta.user_club_id or 0]
        assert all(f.building_to is None for f in user.values())  # never the coach's
        assert conn.execute(text("SELECT COUNT(*) FROM college_program WHERE balance_cents < 0")
                            ).scalar_one() == 0
        conn.rollback()
