"""Club finances (W3): every club's money as a career begins, and how it moves.

Skipped when the base world hasn't been built (it needs the locally downloaded EA FC 27 file,
which isn't in the repository)."""

import shutil
from collections import defaultdict
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, select, text

from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.persistence.schema import club_finance
from footsim.world.career import advance, initialize_career
from footsim.world.context import get_world
from footsim.world.finance import (
    Entry,
    _move_confidence,
    club_leagues,
    initialize_finances,
    ledger_mismatches,
    post,
    projected_revenue_cents,
    settle_month,
    wage_bills,
)
from footsim.world.meta import read_meta
from footsim.world.season import _league_positions

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


# A whole season, watched, and the rollover into the next.


@pytest.fixture(scope="module")
def season(tmp_path_factory: pytest.TempPathFactory) -> Engine:
    engine = _new_career(Path(tmp_path_factory.mktemp("finance_season")))
    with engine.begin() as conn:
        result = advance(conn, get_world(), max_days=400)
    assert result.stop == "season_end"
    return engine


def _season_dates(conn: Connection, season_id: int) -> tuple[date, date]:
    r = conn.execute(text("SELECT start_date, end_date FROM season WHERE id = :s"),
                     {"s": season_id}).one()
    return date.fromisoformat(r.start_date), date.fromisoformat(r.end_date)


def _firsts(start: date, end: date) -> int:
    """First days of a month after ``start``, up to ``end`` (inclusive)."""
    count, year, month = 0, start.year, start.month
    while True:
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        if date(year, month, 1) > end:
            return count
        count += 1


def test_a_season_keeps_every_balance_its_ledger(season: Engine) -> None:
    with season.connect() as conn:
        assert ledger_mismatches(conn) == []


def test_every_club_settles_once_a_month(season: Engine) -> None:
    with season.connect() as conn:
        start, end = _season_dates(conn, 1)
        clubs = conn.execute(text("SELECT COUNT(*) FROM club_finance")).scalar_one()
        counts = conn.execute(text(
            "SELECT club_id, COUNT(*) AS n FROM finance_ledger WHERE kind = 'month' "
            "GROUP BY club_id")).all()
        settled = {r.settled_on for r in conn.execute(select(club_finance.c.settled_on))}
    expected = _firsts(start, end)
    assert expected == 11  # the career starts on 1 July: its opening covers July
    assert len(counts) == clubs
    assert {r.n for r in counts} == {expected}
    assert len(settled) == 1  # all on the same day


def test_merit_is_paid_once_by_final_position(season: Engine) -> None:
    world = get_world()
    with season.connect() as conn:
        finals = conn.execute(text(
            "SELECT f.competition_id, c.key, f.club_id, f.position FROM league_final f "
            "JOIN competition c ON c.id = f.competition_id WHERE f.season_id = 1")).all()
        prizes = {(r.club_id, r.ref_id): r.amount_cents for r in conn.execute(text(
            "SELECT club_id, ref_id, SUM(amount_cents) AS amount_cents, COUNT(*) AS n "
            "FROM finance_ledger WHERE kind = 'prize' GROUP BY club_id, ref_id HAVING n = 1"))}
        rows = conn.execute(text("SELECT COUNT(*) FROM finance_ledger WHERE kind = 'prize'")
                            ).scalar_one()
    by_league: dict[str, list[tuple[int, int, int]]] = defaultdict(list)
    for r in finals:
        by_league[r.key].append((r.position, r.club_id, r.competition_id))
    assert set(by_league) == set(world.defs.leagues)
    assert rows == sum(len(v) - 1 for v in by_league.values())  # the last club gets nothing
    for key, table in by_league.items():
        table.sort()
        paid = [prizes.get((club, comp), 0) for _, club, comp in table]
        merit, size = world.defs.finance.league_income[key].merit, len(table)
        assert paid == [round(merit * 100 * (size - pos) / (size - 1)) for pos, _, _ in table], key


def test_money_is_booked_to_the_right_season_and_day(season: Engine) -> None:
    with season.connect() as conn:
        start1, end1 = _season_dates(conn, 1)
        start2, _ = _season_dates(conn, 2)
        by_kind = {r.kind: (r.seasons, r.first, r.last) for r in conn.execute(text(
            "SELECT kind, GROUP_CONCAT(DISTINCT season_id) AS seasons, MIN(date) AS first, "
            "MAX(date) AS last FROM finance_ledger GROUP BY kind"))}
    assert by_kind["opening"] == ("1", start1.isoformat(), start1.isoformat())
    assert by_kind["prize"][0] == "1" and by_kind["prize"][2] <= end1.isoformat()
    assert by_kind["parachute"] == ("2", start2.isoformat(), start2.isoformat())
    month = by_kind["month"]
    assert month[0] == "1" and month[2] == date(end1.year, end1.month, 1).isoformat()


def test_relegated_clubs_get_a_parachute_and_promoted_clubs_earn_more(season: Engine) -> None:
    world = get_world()
    income = world.defs.finance.league_income
    with season.connect() as conn:
        before, after = club_leagues(conn, 1), club_leagues(conn, 2)
        parachutes = {r.club_id: r.amount_cents for r in conn.execute(text(
            "SELECT club_id, amount_cents FROM finance_ledger WHERE kind = 'parachute'"))}
        own = {r.club_id: r.club_income_cents for r in conn.execute(select(club_finance))}
    down = [c for c in before if income[after[c][0]].expected < income[before[c][0]].expected]
    up = [c for c in before if income[after[c][0]].expected > income[before[c][0]].expected]
    assert len(down) >= 15 and len(up) >= 15  # every country with divisions moves clubs
    assert set(parachutes) == set(down)
    for c in down:
        lost = income[before[c][0]].expected - income[after[c][0]].expected
        assert parachutes[c] == round(world.defs.finance.parachute * lost * 100)
    for c in up:
        assert (projected_revenue_cents(world, after[c][0], own[c])
                > projected_revenue_cents(world, before[c][0], own[c]))


def test_the_new_season_has_budgets_targets_and_a_calmer_board(season: Engine) -> None:
    world = get_world()
    start = world.defs.finance.board.confidence_start
    with season.connect() as conn:
        leagues = club_leagues(conn, 2)
        rows = conn.execute(select(club_finance)).all()
    assert {r.budget_season_id for r in rows} == {2}
    by_league: dict[int, list[int]] = defaultdict(list)
    for r in rows:
        if r.club_id in leagues:
            by_league[leagues[r.club_id][1]].append(r.board_target)
    for got in by_league.values():
        assert sorted(got) == list(range(1, len(got) + 1))
    confidence = [r.board_confidence for r in rows if r.club_id in leagues]
    # The season moved the board's mind, and the new season brought it halfway back.
    assert min(confidence) < start < max(confidence)
    assert all(start - 50 <= c <= start + 50 for c in confidence)


def test_no_balance_explodes_or_collapses_in_a_season(season: Engine) -> None:
    """The recurring money (income, wages, costs, prizes) keeps every balance in bounds. Fees
    are left out: a club that sells well can bank several years' revenue (the market's own
    tests cover transfers)."""
    world = get_world()
    with season.connect() as conn:
        leagues = club_leagues(conn, 1)
        rows = conn.execute(select(club_finance)).all()
        fees = dict(conn.execute(text(
            "SELECT club_id, SUM(amount_cents) FROM finance_ledger WHERE kind = 'transfer' "
            "GROUP BY club_id")).all())
    for r in rows:
        key = leagues[r.club_id][0] if r.club_id in leagues else None
        revenue = projected_revenue_cents(world, key, r.club_income_cents)
        if revenue == 0:
            continue
        recurring = r.balance_cents - fees.get(r.club_id, 0)
        assert -0.25 * revenue < recurring < 1.5 * revenue, (r.club_id, key)


def test_the_users_club_gets_its_month_itemised_and_only_once(season: Engine) -> None:
    world = get_world()
    with season.begin() as conn:
        meta = read_meta(conn)
        assert meta.current_date.day == 1  # the season ended; the 1st of July is next
        user = club_leagues(conn, meta.season_id)
        club_id = min(c for c, (k, _) in user.items() if k == "ENG4")
        as_user = replace(meta, user_club_id=club_id)
        positions = _league_positions(conn, world, as_user)
        rows = conn.execute(text("SELECT COUNT(*) FROM finance_ledger")).scalar_one()
        confidence = text("SELECT club_id, board_confidence FROM club_finance ORDER BY club_id")
        last_id = conn.execute(text("SELECT MAX(id) FROM finance_ledger")).scalar_one()
        settle_month(conn, world, as_user, meta.current_date, positions)
        kinds = {r.kind: r.amount_cents for r in conn.execute(text(
            "SELECT kind, amount_cents FROM finance_ledger WHERE club_id = :c AND id > :i"),
            {"c": club_id, "i": last_id})}
        assert set(kinds) == {"broadcast", "club_income", "wages", "operating"}
        assert kinds["broadcast"] == round(
            world.defs.finance.league_income["ENG4"].base * 100 / 12)
        assert kinds["wages"] < 0 and kinds["operating"] < 0
        settled = conn.execute(text("SELECT COUNT(*) FROM finance_ledger")).scalar_one()
        assert settled == rows + 4 + (conn.execute(text(
            "SELECT COUNT(*) FROM club_finance")).scalar_one() - 1)
        board = conn.execute(confidence).all()
        settle_month(conn, world, as_user, meta.current_date, positions)  # again: nothing
        assert conn.execute(text("SELECT COUNT(*) FROM finance_ledger")).scalar_one() == settled
        assert conn.execute(confidence).all() == board
        assert ledger_mismatches(conn) == []
        conn.rollback()


def test_the_board_warms_to_a_club_above_its_target_and_cools_below_it(career: Engine) -> None:
    rules = get_world().defs.finance.board
    with career.begin() as conn:
        a, b, c, d, e = conn.execute(text(
            "SELECT club_id FROM club_finance ORDER BY club_id LIMIT 5")).scalars().all()
        conn.execute(text("UPDATE club_finance SET board_target = 10, board_confidence = :v "
                          "WHERE club_id = :c"),
                     [{"c": a, "v": 60}, {"c": b, "v": 60}, {"c": c, "v": 98}, {"c": d, "v": 3},
                      {"c": e, "v": 60}])
        _move_confidence(conn, get_world(), {
            a: (7, 20),    # three places above target
            b: (11, 20),   # one below
            c: (1, 20),    # far above, near the top of the scale
            d: (20, 20),   # far below, near the bottom
            e: (1, rules.min_played - 1),  # too early to judge
        })
        got = dict(conn.execute(text(
            "SELECT club_id, board_confidence FROM club_finance WHERE club_id IN "
            "(:a, :b, :c, :d, :e)"), {"a": a, "b": b, "c": c, "d": d, "e": e}).all())
        conn.rollback()
    assert got[a] == 60 + round(3 * rules.per_place)
    assert got[b] == 60 - round(rules.per_place)
    assert got[c] == 100 and got[d] == 0  # capped by max_step, clamped to the scale
    assert got[e] == 60
