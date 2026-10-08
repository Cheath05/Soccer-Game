"""Moving players (W4-3): one club owns a player, the money moves with him, and every move,
the AI's or the user's, obeys the same rules.

Skipped when the base world hasn't been built (it needs the locally downloaded EA FC 27 file,
which isn't in the repository)."""

import json
import shutil
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import Connection, Engine, select, text
from sqlalchemy.exc import IntegrityError

from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.persistence.schema import club_finance, tactic
from footsim.transfers.valuation import years_old
from footsim.world.career import initialize_career
from footsim.world.context import get_world
from footsim.world.finance import (
    ledger_mismatches,
    set_sandbox_budget,
    signing_cost_cents,
    weeks_left,
)
from footsim.world.meta import CareerMeta, read_meta
from footsim.world.transfers import (
    Move,
    MoveRefused,
    complete_move,
    initialize_value_premiums,
    owner_contract,
    player_values,
    senior_squad,
    validate_move,
)

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
OPEN = date(2026, 7, 20)  # England's summer window
CLOSED = date(2026, 10, 1)
END = date(2029, 6, 30)


@pytest.fixture(scope="module")
def career(tmp_path_factory: pytest.TempPathFactory) -> Engine:
    path = Path(tmp_path_factory.mktemp("transfers")) / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, get_world(), None, None, seed=5)
    return engine


@pytest.fixture
def conn(career: Engine) -> Iterator[Connection]:
    """A transaction that's rolled back afterwards: every test starts from the same world."""
    with career.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


def _clubs(conn: Connection, key: str) -> list[int]:
    return list(conn.execute(text(
        "SELECT m.club_id FROM club_league_membership m JOIN competition c "
        "ON c.id = m.competition_id WHERE c.key = :k AND m.season_id = 1 ORDER BY m.club_id"),
        {"k": key}).scalars())


def _outfielder(conn: Connection, club_id: int) -> int:
    """A senior outfield player of the club, its last by id."""
    return int(conn.execute(text(
        "SELECT k.person_id FROM contract k WHERE k.club_id = :c AND k.is_active = 1 "
        "AND k.kind = 'player' AND (SELECT position FROM player_position pp "
        "  WHERE pp.player_id = k.person_id ORDER BY familiarity DESC, position LIMIT 1) != 'GK' "
        "ORDER BY k.person_id DESC LIMIT 1"), {"c": club_id}).scalar_one())


def _money(conn: Connection, club_id: int) -> tuple[int, int]:
    r = conn.execute(select(club_finance.c.balance_cents, club_finance.c.transfer_budget_cents)
                     .where(club_finance.c.club_id == club_id)).one()
    return int(r.balance_cents), int(r.transfer_budget_cents)


def _meta(conn: Connection) -> CareerMeta:
    return read_meta(conn)


def test_a_transfer_moves_the_player_once_and_the_money_with_him(conn: Connection) -> None:
    world = get_world()
    buyer, seller = _clubs(conn, "ENG1")[:2]
    player = _outfielder(conn, seller)
    conn.execute(tactic.delete().where(tactic.c.club_id == seller))
    conn.execute(tactic.insert().values(club_id=seller, formation="4-4-2", roles="{}",
                                        lineup=json.dumps({"ST1": player}),
                                        instructions="{}"))
    fee, wage = 5_000_000_00, 50_000_00
    old_wage = int(conn.execute(text(
        "SELECT wage_weekly_cents FROM contract WHERE person_id = :p AND is_active = 1"),
        {"p": player}).scalar_one())
    weeks = weeks_left(conn, 1, OPEN)
    buyer_before, seller_before = _money(conn, buyer), _money(conn, seller)
    news = complete_move(conn, world, _meta(conn), Move(player, buyer, fee, wage, END), OPEN)
    assert "joins" in news[0] and "€5M" in news[0]

    owners = conn.execute(text(
        "SELECT club_id, start_date, wage_weekly_cents FROM contract "
        "WHERE person_id = :p AND is_active = 1"), {"p": player}).all()
    assert [(r.club_id, r.start_date, r.wage_weekly_cents) for r in owners] == [
        (buyer, OPEN.isoformat(), wage)]
    history = conn.execute(text("SELECT * FROM transfer WHERE player_id = :p"),
                           {"p": player}).one()
    assert (history.from_club_id, history.to_club_id, history.kind, history.fee_cents) == (
        seller, buyer, "transfer", fee)
    assert not history.by_user

    # The money: the buyer pays exactly what the seller receives, both through the ledger.
    buyer_after, seller_after = _money(conn, buyer), _money(conn, seller)
    assert buyer_after[0] == buyer_before[0] - fee and seller_after[0] == seller_before[0] + fee
    # The budgets: the buyer's pays the fee and his new wage for the rest of the season; the
    # seller's gets back its share of the fee and the wage it no longer pays for those weeks.
    cost = fee + round(wage * weeks)
    assert cost == signing_cost_cents(fee, wage, weeks) and cost > fee
    assert buyer_after[1] == buyer_before[1] - cost
    assert seller_after[1] == seller_before[1] + round(world.defs.finance.reinvest * fee) + round(
        old_wage * weeks)
    rows = conn.execute(text(
        "SELECT club_id, amount_cents, ref_id FROM finance_ledger WHERE kind = 'transfer'")).all()
    assert sorted((r.club_id, r.amount_cents) for r in rows) == sorted(
        [(buyer, -fee), (seller, fee)])
    assert {r.ref_id for r in rows} == {history.id}
    assert ledger_mismatches(conn) == []

    # The seller's saved line-up lets him go.
    lineup = conn.execute(select(tactic.c.lineup).where(tactic.c.club_id == seller)).scalar_one()
    assert lineup is None  # he was its only pick: the line-up goes back to automatic


def test_the_database_refuses_a_second_owner(conn: Connection) -> None:
    buyer, seller = _clubs(conn, "ENG2")[:2]
    player = _outfielder(conn, seller)
    with pytest.raises(IntegrityError), conn.begin_nested():
        conn.execute(text(
            "INSERT INTO contract (person_id, club_id, kind, start_date, end_date, "
            "wage_weekly_cents, is_active, listed) VALUES (:p, :c, 'player', '2026-07-01', "
            "'2028-06-30', 100, 1, 0)"), {"p": player, "c": buyer})


def test_every_move_obeys_the_same_rules(conn: Connection) -> None:
    world, meta = get_world(), _meta(conn)
    buyer, seller = _clubs(conn, "ENG3")[:2]
    player = _outfielder(conn, seller)
    budget = _money(conn, buyer)[1]
    refusals = {
        "window is closed": (Move(player, buyer, 1_000_00, 1_000_00, END), CLOSED),
        "beyond the budget": (Move(player, buyer, budget + 1, 1_000_00, END), OPEN),
        "already plays": (Move(player, seller, 0, 1_000_00, END), OPEN),
        "run beyond today": (Move(player, buyer, 0, 1_000_00, OPEN), OPEN),
        "can't be negative": (Move(player, buyer, -1, 1_000_00, END), OPEN),
    }
    assert budget > 0
    refusals["below the minimum"] = (Move(player, buyer, 0, 1, END), OPEN)
    refusals["release has no fee"] = (Move(player, None, 1, 0), OPEN)
    retired = conn.execute(text("SELECT person_id FROM player WHERE retired_on IS NULL "
                                "ORDER BY person_id LIMIT 1")).scalar_one()
    conn.execute(text("UPDATE player SET retired_on = '2026-07-01' WHERE person_id = :p"),
                 {"p": retired})
    refusals["No such player"] = (Move(retired, buyer, 0, 1_000_00, END), OPEN)
    # The same function judges every move: whoever makes it, the reasons are the same.
    for reason, (move, day) in refusals.items():
        with pytest.raises(MoveRefused, match=reason):
            validate_move(conn, world, meta, move, day)
    # Nothing was written by the refusals.
    assert conn.execute(text("SELECT COUNT(*) FROM transfer")).scalar_one() == 0
    assert owner_contract(conn, player).club_id == seller  # type: ignore[union-attr]


def test_a_club_keeps_enough_players_and_keepers(conn: Connection) -> None:
    world, meta = get_world(), _meta(conn)
    rules = world.defs.lifecycle.squads
    buyer, seller = _clubs(conn, "ENG4")[:2]
    seniors = list(conn.execute(text(
        "SELECT k.person_id, (SELECT position FROM player_position pp WHERE pp.player_id = "
        "k.person_id ORDER BY familiarity DESC, position LIMIT 1) AS pos FROM contract k "
        "WHERE k.club_id = :c AND k.is_active = 1 AND k.kind = 'player' ORDER BY k.person_id"),
        {"c": seller}))
    keepers = [r.person_id for r in seniors if r.pos == "GK"]
    outfield = [r.person_id for r in seniors if r.pos != "GK"]
    # Keepers go down to their floor, then one more is refused.
    while len(keepers) > rules.user_min_keepers:
        complete_move(conn, world, meta, Move(keepers.pop(), None), OPEN)
    with pytest.raises(MoveRefused, match="keepers"):
        validate_move(conn, world, meta, Move(keepers[-1], buyer, 0, 2_000_00, END), OPEN)
    # Outfielders down to the squad's floor, then one more is refused.
    while len(keepers) + len(outfield) > rules.user_min_players:
        complete_move(conn, world, meta, Move(outfield.pop(), None), OPEN)
    with pytest.raises(MoveRefused, match="senior players"):
        validate_move(conn, world, meta, Move(outfield[-1], buyer, 0, 2_000_00, END), OPEN)


def test_a_released_player_is_a_free_agent_and_signs_for_nothing(conn: Connection) -> None:
    world, meta = get_world(), _meta(conn)
    buyer, seller = _clubs(conn, "ENG2")[2:4]
    player = _outfielder(conn, seller)
    complete_move(conn, world, meta, Move(player, None, by_user=True), OPEN)
    assert owner_contract(conn, player) is None
    with pytest.raises(MoveRefused, match="no club to leave"):
        validate_move(conn, world, meta, Move(player, None), OPEN)
    with pytest.raises(MoveRefused, match="costs no fee"):
        validate_move(conn, world, meta, Move(player, buyer, 100, 2_000_00, END), OPEN)
    before = _money(conn, buyer)
    news = complete_move(conn, world, meta, Move(player, buyer, 0, 2_000_00, END), OPEN)
    assert "free transfer" in news[0]
    assert owner_contract(conn, player).club_id == buyer  # type: ignore[union-attr]
    # No fee, so no cash moves; his wage for the rest of the season comes out of the budget.
    after = _money(conn, buyer)
    assert after[0] == before[0]
    assert after[1] == before[1] - round(2_000_00 * weeks_left(conn, 1, OPEN))
    kinds = conn.execute(text("SELECT kind FROM transfer WHERE player_id = :p ORDER BY id"),
                         {"p": player}).scalars().all()
    assert kinds == ["release", "free"]


def test_a_release_changes_no_budget_and_no_cash(conn: Connection) -> None:
    seller = _clubs(conn, "ENG3")[1]
    player = _outfielder(conn, seller)
    before = _money(conn, seller)
    complete_move(conn, get_world(), _meta(conn), Move(player, None, by_user=True), OPEN)
    assert owner_contract(conn, player) is None
    assert _money(conn, seller) == before  # no severance, and no money for dumping his wage


def test_values_carry_each_players_own_premium(conn: Connection) -> None:
    world = get_world()
    listed = dict(conn.execute(text(
        "SELECT person_id, value_eur_cents / 100 FROM player WHERE value_eur_cents > 0 "
        "AND retired_on IS NULL ORDER BY value_eur_cents DESC LIMIT 60")).all())
    values = player_values(conn, world, OPEN, list(listed))
    ratio = np.array([np.log(values[p] / listed[p]) for p in listed if p in values])
    # The stars keep most of their Transfermarkt price (the model alone has them ~0.6x).
    assert abs(float(np.median(ratio))) < 0.25
    unknown = conn.execute(text(
        "SELECT COUNT(*) FROM player WHERE value_eur_cents IS NULL AND retired_on IS NULL "
        "AND value_premium != 0")).scalar_one()
    assert unknown == 0
    before = conn.execute(text("SELECT SUM(value_premium) FROM player")).scalar_one()
    initialize_value_premiums(conn, world, CLOSED)  # once only
    assert conn.execute(text("SELECT SUM(value_premium) FROM player")).scalar_one() == before


def test_a_fee_free_deal_between_clubs_moves_no_cash_but_the_wages_move_the_budgets(
        conn: Connection) -> None:
    buyer, seller = _clubs(conn, "ESP1")[:2]
    player = _outfielder(conn, seller)
    old_wage = int(conn.execute(text(
        "SELECT wage_weekly_cents FROM contract WHERE person_id = :p AND is_active = 1"),
        {"p": player}).scalar_one())
    weeks = weeks_left(conn, 1, OPEN)
    (buyer_cash, buyer_budget), (seller_cash, seller_budget) = (
        _money(conn, buyer), _money(conn, seller))
    complete_move(conn, get_world(), _meta(conn), Move(player, buyer, 0, 3_000_00, END), OPEN)
    assert _money(conn, buyer) == (buyer_cash, buyer_budget - round(3_000_00 * weeks))
    assert _money(conn, seller) == (seller_cash, seller_budget + round(old_wage * weeks))
    assert owner_contract(conn, player).club_id == buyer  # type: ignore[union-attr]


def test_the_budget_is_what_a_club_may_spend_on_fees_and_new_wages(conn: Connection) -> None:
    world, meta = get_world(), _meta(conn)
    buyer, seller = _clubs(conn, "ENG2")[:2]
    player = _outfielder(conn, seller)
    weeks = weeks_left(conn, 1, OPEN)
    budget = _money(conn, buyer)[1]
    assert budget > 0
    # A wage alone can be too much: no fee, but a wage that costs more than the budget over the
    # rest of the season is refused, and one that costs exactly the budget is not.
    too_much = int(budget / weeks) + 100
    assert signing_cost_cents(0, too_much, weeks) > budget
    with pytest.raises(MoveRefused, match="That's beyond the budget"):
        validate_move(conn, world, meta, Move(player, buyer, 0, too_much, END), OPEN)
    wage = 40_000_00
    fee = budget - round(wage * weeks)
    assert fee > 0
    with pytest.raises(MoveRefused, match="beyond the budget"):
        validate_move(conn, world, meta, Move(player, buyer, fee + 1, wage, END), OPEN)
    complete_move(conn, world, meta, Move(player, buyer, fee, wage, END, by_user=True), OPEN)
    assert _money(conn, buyer)[1] == 0  # all of it spent
    # With nothing left, even a fee-free signing on the minimum wage is beyond the budget.
    other = _outfielder(conn, _clubs(conn, "ENG2")[3])
    minimum = round(world.defs.wage_levels.minimum_weekly_wage * 100)
    with pytest.raises(MoveRefused, match="beyond the budget"):
        validate_move(conn, world, meta, Move(other, buyer, 0, minimum, END), OPEN)


def test_a_sandbox_budget_of_x_buys_x_of_fees_and_wages(conn: Connection) -> None:
    """The sandbox: a budget of X is X to spend on the transfer market and wages together, and
    the cash is really there (the owner put it in)."""
    world, meta = get_world(), _meta(conn)
    buyer, seller = _clubs(conn, "ENG4")[:2]
    player = _outfielder(conn, seller)
    x = 10_000_000_000_00  # EUR 10bn, the most the sandbox allows
    set_sandbox_budget(conn, meta, buyer, x)
    balance, budget = _money(conn, buyer)
    assert budget == x and balance >= x
    weeks = weeks_left(conn, 1, OPEN)
    wage = 400_000_00  # EUR 400,000 a week
    fee = 9_000_000_000_00  # EUR 9bn: spend most of it on a fee...
    complete_move(conn, world, meta, Move(player, buyer, fee, wage, END, by_user=True), OPEN)
    assert _money(conn, buyer) == (balance - fee, x - fee - round(wage * weeks))
    # ...and the rest of it on fees and wages together, to the last cent.
    rest = _money(conn, buyer)[1]
    other = _outfielder(conn, _clubs(conn, "ENG4")[2])
    fee2 = rest - round(wage * weeks)
    with pytest.raises(MoveRefused, match="beyond the budget"):
        validate_move(conn, world, meta, Move(other, buyer, fee2 + 1, wage, END), OPEN)
    complete_move(conn, world, meta, Move(other, buyer, fee2, wage, END, by_user=True), OPEN)
    assert _money(conn, buyer)[1] == 0
    assert _money(conn, buyer)[0] >= 0  # the cash covered every fee
    assert ledger_mismatches(conn) == []


def test_weeks_left_run_to_the_seasons_end_and_never_below_one(conn: Connection) -> None:
    end = date.fromisoformat(conn.execute(text("SELECT end_date FROM season WHERE id = 1"))
                             .scalar_one())
    assert weeks_left(conn, 1, end - timedelta(days=70)) == 10
    assert weeks_left(conn, 1, end - timedelta(days=10)) == pytest.approx(10 / 7)
    assert weeks_left(conn, 1, end - timedelta(days=3)) == 1  # at least a week
    assert weeks_left(conn, 1, end) == 1
    assert weeks_left(conn, 1, end + timedelta(days=20)) == 1


def test_grown_up_youngsters_count_in_the_senior_squad(conn: Connection) -> None:
    world = get_world()
    club = _clubs(conn, "ENG3")[0]
    adult = world.defs.lifecycle.youth.contract_age
    player = _outfielder(conn, club)
    before = senior_squad(conn, world, club, OPEN)
    conn.execute(text("UPDATE contract SET kind = 'youth' WHERE person_id = :p AND is_active = 1"),
                 {"p": player})
    born = conn.execute(text("SELECT birth_date FROM person WHERE id = :p"),
                        {"p": player}).scalar_one()
    old_enough = years_old(born, OPEN) >= adult
    assert (player in senior_squad(conn, world, club, OPEN)) is old_enough
    assert len(before) >= len(senior_squad(conn, world, club, OPEN))
