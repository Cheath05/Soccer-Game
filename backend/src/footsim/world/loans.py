"""Loans (W4-8; docs/plans/w3-w4-finances-transfers.md, "Contracts and loans").

A loan is a contract row of kind ``loan`` at the borrowing club, beside his permanent contract
at his parent club. Its wage is the borrower's share of his wage. The ``playing`` view puts him
in the borrower's squad, and ``wage_bills`` charges each club its share. It ends on its end date,
and he's back without a write to his permanent contract.

AI clubs and the user go through the same two functions (``validate_loan``, ``start_loan``):
- the borrower's window is open;
- the borrower can pay its share for the weeks left in the season;
- the parent keeps its senior and keeper floors;
- the borrower stays within the squad limit;
- the loan ends no later than his contract;
- he isn't on loan already.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Connection, text

from footsim.world.context import World
from footsim.world.finance import signing_cost_cents, weeks_left
from footsim.world.meta import CareerMeta
from footsim.world.squads import club_name, display_name
from footsim.world.transfers import (
    MoveRefused,
    _check_seller,
    _drop_from_lineup,
    on_loan,
    owner_contract,
    senior_squad,
)
from footsim.world.windows import club_window_nation, window_open


@dataclass(frozen=True)
class Loan:
    player_id: int
    borrower_id: int
    end: date
    share: float  # of his weekly wage the borrower pays (0 to 1)
    by_user: bool = False


def validate_loan(conn: Connection, world: World, meta: CareerMeta, loan: Loan,
                  day: date) -> None:
    """Raise MoveRefused, with the reason, unless ``loan`` can start on ``day``."""
    alive = conn.execute(text("SELECT retired_on FROM player WHERE person_id = :p"),
                         {"p": loan.player_id}).first()
    if alive is None or alive.retired_on is not None:
        raise MoveRefused("No such player.")
    owner = owner_contract(conn, loan.player_id)
    if owner is None:
        raise MoveRefused("A free agent can't be loaned: sign him instead.")
    if owner.club_id == loan.borrower_id:
        raise MoveRefused("He already belongs to that club.")
    if on_loan(conn, loan.player_id):
        raise MoveRefused("He's already out on loan.")
    if not 0.0 <= loan.share <= 1.0:
        raise MoveRefused("The borrower pays between none and all of his wage.")
    if loan.end <= day or loan.end.isoformat() > owner.end_date:
        raise MoveRefused("A loan ends after today and before his contract does.")
    nation = club_window_nation(conn, loan.borrower_id, meta.season_id)
    if not window_open(world, nation, meta.season_id, day):
        raise MoveRefused("The transfer window is closed.")
    budget = conn.execute(text("SELECT transfer_budget_cents FROM club_finance "
                               "WHERE club_id = :c"), {"c": loan.borrower_id}).scalar()
    cost = signing_cost_cents(0, round(loan.share * owner.wage_weekly_cents),
                              weeks_left(conn, meta.season_id, day))
    if budget is None or cost > budget:
        raise MoveRefused("That's beyond the budget.")
    if (len(senior_squad(conn, world, loan.borrower_id, day)) + 1
            > world.defs.lifecycle.squads.max_players):
        raise MoveRefused("The squad is full.")
    _check_seller(conn, world, owner.club_id, loan.player_id, day)


def start_loan(conn: Connection, world: World, meta: CareerMeta, loan: Loan,
               day: date) -> str:
    """Make ``loan`` (checked first). Returns the news."""
    validate_loan(conn, world, meta, loan, day)
    owner = owner_contract(conn, loan.player_id)
    assert owner is not None
    share_cents = round(loan.share * owner.wage_weekly_cents)
    conn.execute(text(
        "INSERT INTO contract (person_id, club_id, kind, start_date, end_date, "
        "wage_weekly_cents, release_clause_cents, is_active, listed) VALUES "
        "(:p, :b, 'loan', :s, :e, :w, NULL, 1, 0)"),
        {"p": loan.player_id, "b": loan.borrower_id, "s": day.isoformat(),
         "e": loan.end.isoformat(), "w": share_cents})
    conn.execute(text(
        "INSERT INTO transfer (player_id, from_club_id, to_club_id, date, season_id, kind, "
        "fee_cents, wage_weekly_cents, contract_end, by_user) VALUES "
        "(:p, :f, :t, :d, :s, 'loan', 0, :w, :e, :u)"),
        {"p": loan.player_id, "f": owner.club_id, "t": loan.borrower_id, "d": day.isoformat(),
         "s": meta.season_id, "w": share_cents, "e": loan.end.isoformat(),
         "u": int(loan.by_user)})
    cost = signing_cost_cents(0, share_cents, weeks_left(conn, meta.season_id, day))
    conn.execute(text("UPDATE club_finance SET transfer_budget_cents = transfer_budget_cents "
                      "- :c WHERE club_id = :b"), {"c": cost, "b": loan.borrower_id})
    _drop_from_lineup(conn, owner.club_id, loan.player_id)
    return (f"{_name(conn, loan.player_id)} joins {club_name(conn, loan.borrower_id)} on loan "
            f"from {club_name(conn, owner.club_id)} until {loan.end.strftime('%B %Y')}.")


def end_loans(conn: Connection, meta: CareerMeta, day: date) -> list[str]:
    """Loans whose end date has passed end: each player is back at his parent club. Returns the
    news of the user's."""
    rows = conn.execute(text(
        "SELECT l.id, l.person_id, l.club_id AS borrower, o.club_id AS parent FROM contract l "
        "JOIN contract o ON o.person_id = l.person_id AND o.is_active = 1 AND o.kind != 'loan' "
        "WHERE l.is_active = 1 AND l.kind = 'loan' AND l.end_date < :d ORDER BY l.id"),
        {"d": day.isoformat()}).all()
    news = []
    for r in rows:
        conn.execute(text("UPDATE contract SET is_active = 0 WHERE id = :id"), {"id": r.id})
        conn.execute(text(
            "INSERT INTO transfer (player_id, from_club_id, to_club_id, date, season_id, kind, "
            "fee_cents, wage_weekly_cents, contract_end, by_user) VALUES "
            "(:p, :f, :t, :d, :s, 'loan_return', 0, 0, NULL, 0)"),
            {"p": r.person_id, "f": r.borrower, "t": r.parent, "d": day.isoformat(),
             "s": meta.season_id})
        _drop_from_lineup(conn, r.borrower, r.person_id)
        if meta.user_club_id in (r.borrower, r.parent):
            news.append(f"{_name(conn, r.person_id)}'s loan at {club_name(conn, r.borrower)} "
                        "is over.")
    return news


def _name(conn: Connection, player_id: int) -> str:
    who = conn.execute(text("SELECT first_name, last_name, known_as FROM person WHERE id = :p"),
                       {"p": player_id}).one()
    return display_name(who.first_name, who.last_name, who.known_as)

