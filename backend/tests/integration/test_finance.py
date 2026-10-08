"""Club finances (W3, simplified in W3-4): every club's money as a career begins, and how it
moves: one budget for fees and wages, the user's optional board, monthly settlements, the changes
in them, merit and cup prize money.

Skipped when the base world hasn't been built (it needs the locally downloaded EA FC 27 file,
which isn't in the repository)."""

import shutil
from collections import defaultdict
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, select, text, update

from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.persistence.schema import club_finance, competition, cup_tie
from footsim.world.career import advance, initialize_career
from footsim.world.context import World, get_world
from footsim.world.cups import cup_prize_cents, progress_cups
from footsim.world.finance import (
    Entry,
    _move_confidence,
    club_leagues,
    initialize_finances,
    ledger_mismatches,
    monthly_parts,
    post,
    projected_revenue_cents,
    rate_changes,
    season_profit_cents,
    set_board_enabled,
    set_budgets,
    set_sandbox_budget,
    settle_month,
    wage_bills,
)
from footsim.world.meta import read_meta
from footsim.world.season import _league_positions

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


def _new_career(directory: Path, club_id: int | None = None, board_enabled: bool = True) -> Engine:
    path = directory / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, get_world(), club_id, "Tester" if club_id else None, seed=5,
                          board_enabled=board_enabled)
    return engine


@pytest.fixture(scope="module")
def career(tmp_path_factory: pytest.TempPathFactory) -> Engine:
    return _new_career(Path(tmp_path_factory.mktemp("finance")))


def _a_club_in(engine: Engine, key: str, index: int = 0) -> int:
    """A club of league ``key`` in the first season (the base world's clubs, by id)."""
    with engine.connect() as conn:
        return int(conn.execute(text(
            "SELECT m.club_id FROM club_league_membership m JOIN competition c "
            "ON c.id = m.competition_id WHERE c.key = :k AND m.season_id = 1 "
            "ORDER BY m.club_id LIMIT 1 OFFSET :i"), {"k": key, "i": index}).scalar_one())


def _board_budget(world: World, balance: int, revenue: int, bill: int) -> int:
    """The board's budget, restated from the rule: a share of revenue and of cash in hand (none
    in debt), less a year of the wages paid above capacity, never below nothing."""
    rules = world.defs.finance
    if balance < 0:
        return 0
    capacity = round(revenue * rules.wage_budget_ratio / 52)
    plan = round(revenue * rules.budget_share + balance * rules.cash_share)
    return max(0, plan - max(0, bill - capacity) * 52)


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


def test_every_clubs_budget_is_the_boards_plan_less_its_wage_overshoot(career: Engine) -> None:
    """One budget for fees and new wages: a share of revenue and of cash in hand, less a year
    of the wages a club pays above what its income supports (its wage capacity)."""
    world = get_world()
    with career.begin() as conn:
        meta = read_meta(conn)
        leagues = club_leagues(conn, 1)
        bills = wage_bills(conn)
        rows = conn.execute(select(club_finance)).all()
        for r in rows:
            key = leagues[r.club_id][0] if r.club_id in leagues else None
            revenue = projected_revenue_cents(world, key, r.club_income_cents)
            assert r.transfer_budget_cents == _board_budget(
                world, r.balance_cents, revenue, bills.get(r.club_id, 0)), r.club_id
            # The capacity is the weekly bill its revenue supports (shown, not a hard limit).
            assert r.wage_budget_cents == round(
                revenue * world.defs.finance.wage_budget_ratio / 52), r.club_id

        # A club that pays above its capacity has the excess, for a year, taken off its budget.
        club_id = next(c for c, (k, _) in leagues.items() if k == "ENG2")
        before = next(r for r in rows if r.club_id == club_id)
        scale = before.wage_budget_cents * 1.05 / bills[club_id]  # a bill 5% over capacity
        conn.execute(text(
            "UPDATE contract SET wage_weekly_cents = "
            "CAST(ROUND(wage_weekly_cents * :f) AS INTEGER) "
            "WHERE club_id = :c AND is_active = 1"), {"f": scale, "c": club_id})
        bill = wage_bills(conn)[club_id]
        assert bill > before.wage_budget_cents
        set_budgets(conn, world, meta, {club_id})
        after = conn.execute(select(club_finance).where(club_finance.c.club_id == club_id)).one()
        assert after.wage_budget_cents == before.wage_budget_cents
        assert after.transfer_budget_cents == (
            before.transfer_budget_cents - (bill - before.wage_budget_cents) * 52)
        assert 0 < after.transfer_budget_cents < before.transfer_budget_cents

        # A club far over its capacity has no budget at all, not a negative one.
        conn.execute(text("UPDATE contract SET wage_weekly_cents = wage_weekly_cents * 100 "
                          "WHERE club_id = :c AND is_active = 1"), {"c": club_id})
        set_budgets(conn, world, meta, {club_id})
        assert conn.execute(select(club_finance.c.transfer_budget_cents).where(
            club_finance.c.club_id == club_id)).scalar_one() == 0

        # A club in debt has none either, however big its income.
        other = next(c for c, (k, _) in leagues.items() if k == "ENG1")
        post(conn, meta.current_date, meta.season_id, [Entry(other, "adjustment", -(10**13))])
        set_budgets(conn, world, meta, {other})
        assert conn.execute(select(club_finance.c.transfer_budget_cents).where(
            club_finance.c.club_id == other)).scalar_one() == 0
        conn.rollback()


def test_a_user_without_a_board_has_all_their_cash_as_a_budget(career: Engine,
                                                               tmp_path: Path) -> None:
    world = get_world()
    on, off = tmp_path / "on", tmp_path / "off"
    on.mkdir(), off.mkdir()
    user = _a_club_in(career, "ENG3")
    engine_on, engine_off = _new_career(on, user), _new_career(off, user, board_enabled=False)
    with engine_on.connect() as with_board, engine_off.connect() as without:
        assert read_meta(with_board).board_enabled and not read_meta(without).board_enabled
        by_club = {k: {r.club_id: r for r in c.execute(select(club_finance))}
                   for k, c in (("on", with_board), ("off", without))}
        # Everyone else's money is the same either way; the user's budget is all their cash.
        for club_id, row in by_club["on"].items():
            if club_id != user:
                assert by_club["off"][club_id].transfer_budget_cents == row.transfer_budget_cents
        mine_on, mine_off = by_club["on"][user], by_club["off"][user]
        assert mine_off.transfer_budget_cents == mine_off.balance_cents > 0
        assert mine_on.transfer_budget_cents == _board_budget(
            world, mine_on.balance_cents,
            projected_revenue_cents(world, "ENG3", mine_on.club_income_cents),
            wage_bills(with_board)[user])
        assert mine_on.transfer_budget_cents != mine_off.transfer_budget_cents
        # The board's target and confidence are kept either way (hidden when it's off).
        assert mine_off.board_target == mine_on.board_target and mine_off.board_target is not None
        assert mine_off.board_confidence == mine_on.board_confidence == 60

    # The sandbox gives the same budget with or without a board, and without one the next
    # season's budget is all the cash, sandbox money included.
    with engine_off.begin() as conn:
        meta = read_meta(conn)
        set_sandbox_budget(conn, meta, user, 7_000_000_000_00)
        row = conn.execute(select(club_finance).where(club_finance.c.club_id == user)).one()
        assert row.transfer_budget_cents == 7_000_000_000_00 <= row.balance_cents
        set_budgets(conn, world, meta)
        assert conn.execute(select(club_finance.c.transfer_budget_cents).where(
            club_finance.c.club_id == user)).scalar_one() == row.balance_cents
        assert ledger_mismatches(conn) == []
    engine_on.dispose(), engine_off.dispose()


def test_switching_the_board_works_the_users_budget_out_again_at_once(career: Engine,
                                                                      tmp_path: Path) -> None:
    world = get_world()
    user = _a_club_in(career, "ENG4")
    engine = _new_career(tmp_path, user)

    def budget(conn: Connection) -> int:
        return int(conn.execute(select(club_finance.c.transfer_budget_cents).where(
            club_finance.c.club_id == user)).scalar_one())

    with engine.begin() as conn:
        meta = read_meta(conn)
        row = conn.execute(select(club_finance).where(club_finance.c.club_id == user)).one()
        plan = budget(conn)
        assert plan > 0 and meta.board_enabled
        # Off: all their cash, at once, and the setting is saved.
        set_board_enabled(conn, world, meta, False)
        assert budget(conn) == row.balance_cents != plan
        assert not read_meta(conn).board_enabled
        # Money spent from the budget stays spent: switching to what it already is does nothing,
        # so it isn't a way to refill it.
        conn.execute(update(club_finance).where(club_finance.c.club_id == user).values(
            transfer_budget_cents=1234))
        set_board_enabled(conn, world, meta, False)
        assert budget(conn) == 1234
        # On again: the board's plan, worked out from the cash and wages as they are now.
        set_board_enabled(conn, world, meta, True)
        assert budget(conn) == plan and read_meta(conn).board_enabled
        conn.execute(update(club_finance).where(club_finance.c.club_id == user).values(
            transfer_budget_cents=99))
        set_board_enabled(conn, world, meta, True)
        assert budget(conn) == 99
        # A watch-only career has no board to switch.
        with pytest.raises(ValueError, match="no board"):
            set_board_enabled(conn, world, replace(meta, user_club_id=None), False)
        assert ledger_mismatches(conn) == []
    engine.dispose()


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
    leagues = "ref_id IN (SELECT id FROM competition WHERE type = 'league')"  # not the cups'
    with season.connect() as conn:
        finals = conn.execute(text(
            "SELECT f.competition_id, c.key, f.club_id, f.position FROM league_final f "
            "JOIN competition c ON c.id = f.competition_id WHERE f.season_id = 1")).all()
        prizes = {(r.club_id, r.ref_id): r.amount_cents for r in conn.execute(text(
            "SELECT club_id, ref_id, SUM(amount_cents) AS amount_cents, COUNT(*) AS n "
            f"FROM finance_ledger WHERE kind = 'prize' AND {leagues} "
            "GROUP BY club_id, ref_id HAVING n = 1"))}
        rows = conn.execute(text(
            f"SELECT COUNT(*) FROM finance_ledger WHERE kind = 'prize' AND {leagues}")
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


def test_the_new_seasons_budgets_follow_the_boards_plan(season: Engine) -> None:
    """At the rollover every club's budget is its board's plan, from the revenue its new league
    gives it and the cash and wages it then had. A user without a board gets all their cash
    instead (what the rollover does for them: ``set_budgets`` with their meta)."""
    world = get_world()
    with season.begin() as conn:
        meta = read_meta(conn)
        assert meta.season_id == 2
        leagues = club_leagues(conn, 2)
        bills = wage_bills(conn)
        rows = conn.execute(select(club_finance)).all()
        for r in rows:
            key = leagues[r.club_id][0] if r.club_id in leagues else None
            revenue = projected_revenue_cents(world, key, r.club_income_cents)
            assert r.transfer_budget_cents == _board_budget(
                world, r.balance_cents, revenue, bills.get(r.club_id, 0)), r.club_id
            assert r.wage_budget_cents == round(
                revenue * world.defs.finance.wage_budget_ratio / 52), r.club_id
        assert any(r.transfer_budget_cents > 0 for r in rows)

        user = next(c for c, (k, _) in leagues.items() if k == "ENG2")
        as_user = replace(meta, user_club_id=user, board_enabled=False)
        set_budgets(conn, world, as_user)
        budgets = {r.club_id: r for r in conn.execute(select(club_finance))}
        assert budgets[user].transfer_budget_cents == max(0, budgets[user].balance_cents)
        for r in rows:  # nobody else's budget depends on the user's choice
            if r.club_id != user:
                assert budgets[r.club_id].transfer_budget_cents == r.transfer_budget_cents
                assert budgets[r.club_id].board_target == r.board_target
        assert budgets[user].board_target is not None  # the board's view is kept, only hidden
        set_budgets(conn, world, replace(as_user, board_enabled=True))
        again = conn.execute(select(club_finance.c.transfer_budget_cents).where(
            club_finance.c.club_id == user)).scalar_one()
        assert again == next(r for r in rows if r.club_id == user).transfer_budget_cents
        conn.rollback()


def test_cup_prizes_are_paid_once_to_the_winner_of_each_tie(season: Engine) -> None:
    """Every tie that was played pays its winner that round's prize, once: a bye pays nothing,
    the loser nothing, and every balance is still its ledger."""
    world = get_world()
    with season.connect() as conn:
        ids = {r.key: r.id for r in conn.execute(select(competition.c.id, competition.c.key))}
        paid: dict[tuple[int, int], list[int]] = defaultdict(list)
        for r in conn.execute(text(
                "SELECT club_id, ref_id, amount_cents FROM finance_ledger WHERE kind = 'prize' "
                "AND season_id = 1 AND ref_id IN (SELECT id FROM competition WHERE type = 'cup')")):
            paid[(r.club_id, r.ref_id)].append(r.amount_cents)
        expected: dict[tuple[int, int], list[int]] = defaultdict(list)
        played = 0
        for key, cup in world.defs.cups.items():
            for t in conn.execute(text(
                    "SELECT round, club_a_id, club_b_id, winner_club_id FROM cup_tie "
                    "WHERE season_id = 1 AND competition_id = :c"), {"c": ids[key]}):
                if t.club_b_id is None:
                    continue  # exempt from the round: nothing was won
                assert t.winner_club_id in (t.club_a_id, t.club_b_id), (key, t.round)
                expected[(t.winner_club_id, ids[key])].append(cup_prize_cents(world, cup, t.round))
                played += 1
        assert played > 300
        assert {k: sorted(v) for k, v in paid.items()} == {
            k: sorted(v) for k, v in expected.items()}
        assert sum(len(v) for v in paid.values()) == played
        # The prize rises with the round, to the final's, the cup's biggest.
        for key, cup in world.defs.cups.items():
            prizes = [cup_prize_cents(world, cup, n) for n in range(len(cup.rounds))]
            assert prizes == sorted(prizes) and prizes[-1] > prizes[0], key
        assert ledger_mismatches(conn) == []


def test_a_day_that_runs_again_pays_no_cup_prize_twice(season: Engine) -> None:
    world = get_world()
    with season.begin() as conn:
        _, end = _season_dates(conn, 1)
        meta = replace(read_meta(conn), season_id=1)
        cup = world.defs.cups["FA_CUP"]
        comp = conn.execute(select(competition.c.id).where(competition.c.key == "FA_CUP")
                            ).scalar_one()
        final = conn.execute(text(
            "SELECT id, winner_club_id FROM cup_tie WHERE season_id = 1 AND competition_id = :c "
            "AND round = :r"), {"c": comp, "r": len(cup.rounds) - 1}).one()
        prize = cup_prize_cents(world, cup, len(cup.rounds) - 1)

        def prizes_paid() -> int:
            return int(conn.execute(text(
                "SELECT COUNT(*) FROM finance_ledger WHERE kind = 'prize' AND club_id = :club "
                "AND ref_id = :c AND amount_cents = :a"),
                {"club": final.winner_club_id, "c": comp, "a": prize}).scalar_one())

        assert prizes_paid() == 1
        # As if the final had only just been decided: the winner is worked out and paid once...
        conn.execute(update(cup_tie).where(cup_tie.c.id == final.id).values(winner_club_id=None))
        progress_cups(conn, world, meta, end)
        assert prizes_paid() == 2
        assert conn.execute(select(cup_tie.c.winner_club_id).where(cup_tie.c.id == final.id)
                            ).scalar_one() == final.winner_club_id
        # ...and not again when the day is run again.
        progress_cups(conn, world, meta, end)
        assert prizes_paid() == 2
        assert ledger_mismatches(conn) == []
        conn.rollback()


def test_changes_in_the_month_are_listed_once_when_a_part_moves_notably(career: Engine) -> None:
    """Recurring money shows as the month's profit; what changes in it shows once, when a part
    moves by 5% and by at least 10,000 between two settlements, latest first, at most ten."""
    world = get_world()
    rules = world.defs.finance.display
    assert (rules.change_share, rules.change_amount, rules.changes_shown) == (0.05, 10_000, 10)
    with career.begin() as conn:
        meta = read_meta(conn)
        a, b = conn.execute(text("SELECT club_id FROM club_finance ORDER BY club_id LIMIT 2")
                            ).scalars().all()

        def settle(club: int, day: date, tv: int, own: int, wages: int, running: int) -> None:
            post(conn, day, meta.season_id, [
                Entry(club, "broadcast", tv * 100), Entry(club, "club_income", own * 100),
                Entry(club, "wages", wages * 100), Entry(club, "operating", running * 100)])

        # (TV money, commercial, wages, running costs) a month, in euros.
        months = [
            (date(2026, 8, 1), 5_200_000, 9_000, -3_000_000, -1_000_000),
            (date(2026, 9, 1), 5_200_000, 9_900, -3_000_000, -1_004_000),  # +10% of 9,000: tiny
            (date(2026, 10, 1), 5_200_000, 9_900, -3_100_000, -1_004_000),  # wages +3.3%: <5%
            (date(2026, 11, 1), 800_000, 9_900, -3_400_000, -1_004_000),  # relegated; wages +9.7%
            (date(2026, 12, 1), 800_000, 9_900, -3_400_000, -1_004_000),  # nothing moved
        ]
        for day, *parts in months:
            settle(a, day, *parts)
        got = [(c.date, c.kind, c.before_cents // 100, c.after_cents // 100)
               for c in rate_changes(conn, world, a)]
        assert got == [("2026-11-01", "broadcast", 5_200_000, 800_000),
                       ("2026-11-01", "wages", -3_100_000, -3_400_000)]
        assert rate_changes(conn, world, b) == []  # no itemised settlements, no changes

        for n in range(13):  # TV money swinging every month: only the latest ten are listed
            settle(b, date(2027 + n // 12, n % 12 + 1, 1), 6_000_000 if n % 2 == 0 else 1_000_000,
                   9_000, -3_000_000, -1_000_000)
        swings = rate_changes(conn, world, b)
        assert [c.date for c in swings] == [date(2028, 1, 1).isoformat(), *(
            date(2027, 12 - k, 1).isoformat() for k in range(9))]
        assert {c.kind for c in swings} == {"broadcast"}
        assert ledger_mismatches(conn) == []
        # The year's profit so far counts the months settled, not one-off money.
        assert season_profit_cents(conn, a, meta.season_id) == sum(
            (tv + own + wages + running) * 100 for _, tv, own, wages, running in months)
        post(conn, date(2026, 12, 2), meta.season_id, [Entry(a, "adjustment", 5_000_000_00)])
        assert season_profit_cents(conn, a, meta.season_id) == sum(
            (tv + own + wages + running) * 100 for _, tv, own, wages, running in months)
        conn.rollback()


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
        # They are the month's parts at today's rates: what the finances page shows as profit.
        own_income = conn.execute(select(club_finance.c.club_income_cents).where(
            club_finance.c.club_id == club_id)).scalar_one()
        parts = monthly_parts(world, "ENG4", own_income, wage_bills(conn)[club_id])
        assert kinds == {"broadcast": parts.broadcast, "club_income": parts.club_income,
                         "wages": parts.wages, "operating": parts.operating}
        assert parts.profit == sum(kinds.values())
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
