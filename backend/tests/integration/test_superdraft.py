"""MLS's SuperDraft (W9a B5): a career played to January drafts the college prospects of the
NCAA season just finished. Three rounds in reverse order of the table; the user's club takes the
prospects of its own ranking; picks turn pro, their clubs hold their rights, and the picks are
signed under MLS's rules (Generation adidas on the supplemental roster). Needs the built world."""

import shutil
from datetime import timedelta

import pytest
from sqlalchemy import Connection, Engine, text

from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.world import draft
from footsim.world.career import advance, initialize_career
from footsim.world.college import draft_pool
from footsim.world.context import World, get_world
from footsim.world.meta import read_meta, write_meta
from footsim.world.mls import mls_club_ids
from footsim.world.mls_market import addition_problem
from footsim.world.season import standings

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


def _club(conn: Connection, name: str) -> int:
    return int(conn.execute(text("SELECT id FROM club WHERE name = :n"), {"n": name}).scalar_one())


@pytest.fixture(scope="module")
def drafted(tmp_path_factory: pytest.TempPathFactory) -> tuple[Engine, World, int, list[int],
                                                                list[str]]:
    """A watch-only career played to two weeks before the draft; then the user takes Atlanta
    United (an MLS club), ranks three prospects from the bottom of the pool, and plays on past
    the draft."""
    world = get_world()
    path = tmp_path_factory.mktemp("draft") / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, world, None, None, seed=11)
        when = draft.draft_date(world, conn, 1)
        start = read_meta(conn).current_date
    with engine.begin() as conn:
        advance(conn, world, max_days=(when - start).days - draft.rules(world).reminder_days)
    with engine.begin() as conn:
        meta = read_meta(conn)
        assert meta.current_date == when - timedelta(days=draft.rules(world).reminder_days)
        atlanta = _club(conn, "Atlanta United")
        meta.user_club_id = atlanta
        meta.offer_mode = "wait"  # a bid for one of its players mustn't stop the days here
        write_meta(conn, meta)
        pool = draft_pool(conn, world, meta, 1)
        assert len(pool) >= draft.rules(world).rounds * 30 // 2
        board = [p.player_id for p in pool[-3:]]  # three the scouts wouldn't take early
        draft.set_board(conn, world, meta, atlanta, board)
    news: list[str] = []
    with engine.begin() as conn:
        news += advance(conn, world, max_days=1).messages  # the reminder day
        news += advance(conn, world, max_days=draft.rules(world).reminder_days).messages
    return engine, world, atlanta, board, news


def test_the_draft_is_made_in_order(drafted: tuple[Engine, World, int, list[int], list[str]]
                                    ) -> None:
    engine, world, atlanta, _, news = drafted
    assert any("SuperDraft is on" in m for m in news)
    assert any(m.startswith("The MLS SuperDraft:") for m in news)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM draft_pick WHERE season_id = 1 ORDER BY pick")
                            ).all()
        clubs = mls_club_ids(conn, world, 1)
        assert len(rows) == 30 * draft.rules(world).rounds
        assert len({r.player_id for r in rows}) == len(rows)
        first = [r.club_id for r in rows if r.round == 1]
        assert set(first) == clubs and len(first) == 30
        assert all([r.club_id for r in rows if r.round == k] == first
                   for k in range(2, draft.rules(world).rounds + 1))
        # The first season's order: the table so far (MLS's winter break: as on draft day),
        # worst first.
        comp = int(conn.execute(text("SELECT id FROM competition WHERE key = :k"),
                                {"k": world.defs.mls.league}).scalar_one())
        table = standings(conn, world, read_meta(conn), comp, 1)
        assert first == [r.club_id for r in reversed(table)]
        status = {r.status for r in conn.execute(text(
            "SELECT cp.status FROM college_player cp JOIN draft_pick d "
            "ON d.player_id = cp.player_id WHERE d.season_id = 1"))}
        assert status == {"pro"}
    with engine.begin() as conn:  # made once: running it again changes nothing
        assert draft.run_draft(conn, world, read_meta(conn), read_meta(conn).current_date) == []
        assert conn.execute(text("SELECT COUNT(*) FROM draft_pick")).scalar_one() == len(rows)


def test_the_users_board_and_signings(drafted: tuple[Engine, World, int, list[int], list[str]]
                                      ) -> None:
    engine, world, atlanta, board, news = drafted
    with engine.connect() as conn:
        mine = conn.execute(text(
            "SELECT player_id, signed, round FROM draft_pick WHERE season_id = 1 AND club_id = :c "
            "ORDER BY pick"), {"c": atlanta}).all()
        assert len(mine) == draft.rules(world).rounds
        # The board's prospects were at the bottom of the pool: nobody else took them first.
        assert [r.player_id for r in mine] == board
        assert any(m.startswith("Your SuperDraft picks:") for m in news)
        signed = [r for r in mine if r.signed]
        for r in signed:
            contract = conn.execute(text(
                "SELECT club_id FROM contract WHERE person_id = :p AND is_active = 1 "
                "AND kind = 'player'"), {"p": r.player_id}).scalar()
            assert contract == atlanta
        # AI clubs signed most of their first two rounds' picks.
        early = conn.execute(text(
            "SELECT signed FROM draft_pick WHERE season_id = 1 AND round <= :k AND club_id != :c"),
            {"k": draft.rules(world).ai_sign_rounds, "c": atlanta}).all()
        assert sum(r.signed for r in early) >= len(early) // 2
        # Generation adidas picks are marked for the supplemental roster.
        ga = conn.execute(text(
            "SELECT d.player_id, s.ga_until_season FROM draft_pick d JOIN college_player cp "
            "ON cp.player_id = d.player_id LEFT JOIN mls_player s ON s.player_id = d.player_id "
            "WHERE d.season_id = 1 AND cp.ga = 1")).all()
        assert all(r.ga_until_season is not None and r.ga_until_season >= 1 for r in ga)


def test_rights_keep_other_mls_clubs_off_an_unsigned_pick(
        drafted: tuple[Engine, World, int, list[int], list[str]]) -> None:
    engine, world, atlanta, _, _ = drafted
    with engine.begin() as conn:
        meta = read_meta(conn)
        unsigned = conn.execute(text(
            "SELECT player_id, club_id FROM draft_pick WHERE season_id = 1 AND signed = 0 "
            "ORDER BY pick LIMIT 1")).first()
        if unsigned is None:
            pytest.skip("every pick was signed")
        other = next(c for c in sorted(mls_club_ids(conn, world, 1))
                     if c not in (unsigned.club_id, atlanta))
        problem = addition_problem(conn, world, meta, other, unsigned.player_id, 300_000,
                                   meta.current_date)
        assert problem == "Another MLS club holds his draft rights."
