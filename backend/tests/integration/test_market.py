"""The AI transfer market (W4-5): a watched career trades through the first weeks of a summer
window, by the rules, keeping every invariant, and the same way every time.

Skipped when the base world hasn't been built (it needs the locally downloaded EA FC 27 file,
which isn't in the repository)."""

import shutil
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.world.career import advance, initialize_career
from footsim.world.context import get_world
from footsim.world.finance import ledger_mismatches
from footsim.world.meta import read_meta
from footsim.world.season import after_day

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
UNTIL = date(2026, 7, 21)


def _traded(directory: Path) -> Engine:
    path = directory / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, get_world(), None, None, seed=5)
    with engine.begin() as conn:
        advance(conn, get_world(), max_days=(UNTIL - date(2026, 7, 1)).days)
    return engine


@pytest.fixture(scope="module")
def traded(tmp_path_factory: pytest.TempPathFactory) -> Engine:
    return _traded(Path(tmp_path_factory.mktemp("market")))


def test_clubs_trade_in_the_window(traded: Engine) -> None:
    with traded.connect() as conn:
        deals = conn.execute(text(
            "SELECT COUNT(*), SUM(fee_cents > 0), COUNT(DISTINCT to_club_id) FROM transfer "
            "WHERE kind IN ('transfer', 'free')")).one()
        listed = conn.execute(text("SELECT COUNT(*) FROM contract WHERE listed = 1 "
                                   "AND is_active = 1")).scalar_one()
    count, paid, buyers = deals
    assert count > 200 and paid > 100 and buyers > 150
    assert listed > 50  # clubs put their surplus up for sale


def test_every_move_keeps_the_invariants(traded: Engine) -> None:
    with traded.connect() as conn:
        assert ledger_mismatches(conn) == []
        assert conn.execute(text(
            "SELECT COUNT(*) FROM (SELECT person_id FROM contract WHERE is_active = 1 "
            "AND kind != 'loan' GROUP BY person_id HAVING COUNT(*) > 1)")).scalar_one() == 0
        # Every transfer's fee left the buyer and reached the seller, once.
        unpaid = conn.execute(text(
            "SELECT COUNT(*) FROM transfer t WHERE t.fee_cents > 0 AND (SELECT COUNT(*) "
            "FROM finance_ledger l WHERE l.kind = 'transfer' AND l.ref_id = t.id) != 2"
        )).scalar_one()
        assert unpaid == 0
        assert conn.execute(text(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM finance_ledger WHERE kind = 'transfer'"
        )).scalar_one() == 0  # money moved between clubs: none made or lost
        # Nobody spent beyond the budget, and no player moved twice.
        assert conn.execute(text(
            "SELECT COUNT(*) FROM club_finance WHERE transfer_budget_cents < 0")).scalar_one() == 0
        assert conn.execute(text(
            "SELECT COUNT(*) FROM (SELECT player_id FROM transfer GROUP BY player_id "
            "HAVING COUNT(*) > 1)")).scalar_one() == 0
        # A club that sold kept enough players and keepers to play.
        floor = get_world().defs.lifecycle.squads.user_min_players
        thin = conn.execute(text(
            "SELECT COUNT(*) FROM (SELECT k.club_id, COUNT(*) AS n FROM contract k "
            "WHERE k.is_active = 1 AND k.kind = 'player' AND k.club_id IN "
            "(SELECT from_club_id FROM transfer WHERE from_club_id IS NOT NULL) "
            "GROUP BY k.club_id HAVING n < :floor)"), {"floor": floor}).scalar_one()
        assert thin == 0


def test_the_market_runs_once_a_day(traded: Engine) -> None:
    world = get_world()
    with traded.connect() as conn:
        transaction = conn.begin()
        meta = read_meta(conn)
        before = conn.execute(text("SELECT COUNT(*) FROM transfer")).scalar_one()
        day = date(2026, 7, 20)  # already run
        after_day(conn, world, meta, day)
        assert conn.execute(text("SELECT COUNT(*) FROM transfer")).scalar_one() == before
        transaction.rollback()


def test_the_same_career_trades_the_same_way(traded: Engine, tmp_path: Path) -> None:
    again = _traded(tmp_path)
    query = text("SELECT player_id, from_club_id, to_club_id, date, fee_cents, "
                 "wage_weekly_cents, contract_end FROM transfer ORDER BY id")
    with traded.connect() as a, again.connect() as b:
        assert a.execute(query).all() == b.execute(query).all()
    again.dispose()
