"""Club finances (W3): every club's money as a career begins, and how it moves.

Skipped when the base world hasn't been built (it needs the locally downloaded EA FC 27 file,
which isn't in the repository)."""

import shutil
from collections import defaultdict
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, select, text

from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.persistence.schema import club_finance
from footsim.world.career import initialize_career
from footsim.world.context import get_world
from footsim.world.finance import (
    Entry,
    club_leagues,
    initialize_finances,
    ledger_mismatches,
    post,
    projected_revenue_cents,
    wage_bills,
)
from footsim.world.meta import read_meta

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


def _new_career(directory: Path) -> Engine:
    path = directory / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, get_world(), None, None, seed=5)
    return engine


@pytest.fixture(scope="module")
def career(tmp_path_factory: pytest.TempPathFactory) -> Engine:
    return _new_career(Path(tmp_path_factory.mktemp("finance")))


def _revenue(conn: Connection) -> dict[int, tuple[str | None, int]]:
    leagues = club_leagues(conn, 1)
    world = get_world()
    result = {}
    for r in conn.execute(select(club_finance)):
        key = leagues[r.club_id][0] if r.club_id in leagues else None
        result[r.club_id] = (key, projected_revenue_cents(world, key, r.club_income_cents))
    return result


def test_every_club_has_finances_and_its_balance_is_its_ledger(career: Engine) -> None:
    with career.connect() as conn:
        clubs = conn.execute(text("SELECT COUNT(*) FROM club")).scalar_one()
        assert conn.execute(text("SELECT COUNT(*) FROM club_finance")).scalar_one() == clubs
        assert ledger_mismatches(conn) == []
        opening = conn.execute(text(
            "SELECT COUNT(*) FROM finance_ledger WHERE kind = 'opening'")).scalar_one()
        assert opening == conn.execute(text(
            "SELECT COUNT(*) FROM club_finance WHERE balance_cents != 0")).scalar_one()
        assert opening > 0.95 * clubs
        # Money is whole cents: a stray float would be stored as REAL.
        assert conn.execute(text(
            "SELECT COUNT(*) FROM club_finance WHERE typeof(balance_cents) != 'integer' "
            "OR typeof(club_income_cents) != 'integer' OR typeof(transfer_budget_cents) != "
            "'integer' OR typeof(wage_budget_cents) != 'integer'")).scalar_one() == 0
        assert conn.execute(text(
            "SELECT COUNT(*) FROM finance_ledger WHERE typeof(amount_cents) != 'integer'"
        )).scalar_one() == 0


def test_bigger_leagues_and_bigger_clubs_have_more_money(career: Engine) -> None:
    with career.connect() as conn:
        revenue = _revenue(conn)
        bills = wage_bills(conn)
    by_league: dict[str | None, list[int]] = defaultdict(list)
    for key, value in revenue.values():
        by_league[key].append(value)

    def mean(key: str) -> float:
        return sum(by_league[key]) / len(by_league[key])

    assert mean("ENG1") > mean("ENG2") > mean("ENG3") > mean("ENG4")
    assert mean("ENG1") > mean("ESP1") > mean("ESP2")
    assert mean("GER1") > mean("GER2") > mean("GER3")
    # Within a league, the club paying the most earns the most (its size is in its wages).
    for key in ("ENG1", "ESP1", "ENG4"):
        clubs = [c for c, (k, _) in revenue.items() if k == key]
        assert max(clubs, key=lambda c: revenue[c][1]) == max(clubs, key=lambda c: bills[c])


def test_budgets_leave_room_for_wages_and_spending(career: Engine) -> None:
    with career.connect() as conn:
        bills = wage_bills(conn)
        leagues = club_leagues(conn, 1)
        rows = conn.execute(select(club_finance)).all()
    for r in rows:
        if r.club_id not in leagues:
            continue
        assert r.wage_budget_cents >= bills.get(r.club_id, 0), r.club_id  # room to grow
        assert r.transfer_budget_cents > 0, r.club_id
        assert r.budget_season_id == 1


def test_the_board_expects_each_club_to_finish_where_its_squad_ranks(career: Engine) -> None:
    with career.connect() as conn:
        leagues = club_leagues(conn, 1)
        targets = {r.club_id: r.board_target for r in conn.execute(select(club_finance))}
        bills = wage_bills(conn)
    by_league: dict[int, list[int]] = defaultdict(list)
    for club_id, (_, competition_id) in leagues.items():
        by_league[competition_id].append(targets[club_id])
    for got in by_league.values():
        assert sorted(got) == list(range(1, len(got) + 1))
    # The favourite is one of the league's biggest payers.
    eng1 = [c for c, (k, _) in leagues.items() if k == "ENG1"]
    favourite = next(c for c in eng1 if targets[c] == 1)
    assert favourite in sorted(eng1, key=lambda c: -bills.get(c, 0))[:4]


def test_finances_begin_once(career: Engine) -> None:
    world = get_world()
    with career.begin() as conn:
        before = conn.execute(text("SELECT * FROM club_finance ORDER BY club_id")).all()
        rows = conn.execute(text("SELECT COUNT(*) FROM finance_ledger")).scalar_one()
        initialize_finances(conn, world, read_meta(conn), read_meta(conn).current_date)
        assert conn.execute(text("SELECT COUNT(*) FROM finance_ledger")).scalar_one() == rows
        assert conn.execute(text("SELECT * FROM club_finance ORDER BY club_id")).all() == before
        conn.rollback()


def test_post_moves_balances_with_the_ledger_and_refuses_what_it_cannot_book(
        career: Engine) -> None:
    with career.begin() as conn:
        meta = read_meta(conn)
        club_id = conn.execute(text("SELECT MIN(club_id) FROM club_finance")).scalar_one()
        balance = conn.execute(select(club_finance.c.balance_cents).where(
            club_finance.c.club_id == club_id)).scalar_one()
        post(conn, meta.current_date, meta.season_id, [
            Entry(club_id, "adjustment", 500), Entry(club_id, "adjustment", -200),
            Entry(club_id, "adjustment", 0)])
        assert conn.execute(select(club_finance.c.balance_cents).where(
            club_finance.c.club_id == club_id)).scalar_one() == balance + 300
        assert ledger_mismatches(conn) == []
        with pytest.raises(ValueError, match="no finances"):
            post(conn, meta.current_date, meta.season_id, [Entry(10**9, "adjustment", 1)])
        with pytest.raises(ValueError, match="unknown ledger kinds"):
            post(conn, meta.current_date, meta.season_id, [Entry(club_id, "gift", 1)])
        conn.rollback()


def test_finances_are_the_same_from_the_same_start(career: Engine, tmp_path: Path) -> None:
    other = _new_career(tmp_path)
    query = text("SELECT * FROM club_finance ORDER BY club_id")
    ledger = text("SELECT club_id, date, kind, amount_cents FROM finance_ledger ORDER BY id")
    with career.connect() as a, other.connect() as b:
        assert a.execute(query).all() == b.execute(query).all()
        assert a.execute(ledger).all() == b.execute(ledger).all()
    other.dispose()
