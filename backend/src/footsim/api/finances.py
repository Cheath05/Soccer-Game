"""The user's club's finances page (W3-3, simplified in W3-4): the balance, the budget, a month's
money at today's rates (the same figures ``settle_month`` books), the notable changes in it, the
one-off transactions and, when the user plays with a board, the board's view. Read from
``club_finance`` and ``finance_ledger`` (world/finance.py).

Recurring money is shown once, as the month's profit: a drop in TV money after relegation shows
as one change, not as a lower line in every month. Transactions are one-off money only."""

from typing import Any

from sqlalchemy import Connection, Row, bindparam, select, text

from footsim.api.schemas import (
    BoardOut,
    ChangeOut,
    ClubRef,
    FinancesOut,
    MonthlyOut,
    TransactionOut,
)
from footsim.persistence.schema import club, club_finance
from footsim.world.context import World
from footsim.world.finance import (
    ONE_OFF,
    club_leagues,
    monthly_parts,
    rate_changes,
    season_profit_cents,
    wage_bills,
    weeks_left,
)
from footsim.world.meta import read_meta
from footsim.world.season import standings
from footsim.world.squads import display_name

LABELS = {
    "opening": "Opening balance",
    "broadcast": "League TV money",
    "club_income": "Commercial and matchday",
    "wages": "Wages",
    "operating": "Running costs",
    "prize": "Prize money",
    "parachute": "Parachute payment",
    "transfer": "Transfer",
    "adjustment": "Owner investment",
}

# The board's mood by its confidence (0-100): the lowest confidence for each word.
MOODS = [(80, "Delighted"), (65, "Pleased"), (45, "Satisfied"), (30, "Concerned"), (0, "Unhappy")]


class NoClub(LookupError):
    """A watch-only career has no club of its own."""


def mood(confidence: int | None) -> str:
    if confidence is None:
        return "No view yet"
    return next(word for floor, word in MOODS if confidence >= floor)


def _cents_to_eur(cents: int) -> int:
    return int(round(cents / 100))


def finances(conn: Connection, world: World) -> FinancesOut:
    meta = read_meta(conn)
    club_id = meta.user_club_id
    if club_id is None:
        raise NoClub()
    row = conn.execute(select(club_finance).where(club_finance.c.club_id == club_id)).one()
    name = str(conn.execute(select(club.c.name).where(club.c.id == club_id)).scalar_one())
    league = club_leagues(conn, meta.season_id).get(club_id)
    key = league[0] if league else None
    bill = wage_bills(conn).get(club_id, 0)
    parts = monthly_parts(world, key, row.club_income_cents, bill)
    tv, commercial = _cents_to_eur(parts.broadcast), _cents_to_eur(parts.club_income)
    wages, running = _cents_to_eur(parts.wages), _cents_to_eur(parts.operating)
    board = None
    if meta.board_enabled:
        position, played, size = None, 0, None
        if league is not None:
            table = standings(conn, world, meta, league[1], meta.season_id)
            size = len(table)
            mine = next((r for r in table if r.club_id == club_id), None)
            if mine is not None and mine.played:
                position, played = mine.position, mine.played
        board = BoardOut(target=row.board_target, position=position, played=played,
                         league_size=size, confidence=row.board_confidence,
                         mood=mood(row.board_confidence))
    return FinancesOut(
        club=ClubRef(id=club_id, name=name), season=_season_label(conn, meta.season_id),
        league=world.defs.leagues[key].name if key else None,
        balance_eur=_cents_to_eur(row.balance_cents),
        budget_eur=_cents_to_eur(row.transfer_budget_cents),
        wage_bill_weekly_eur=_cents_to_eur(bill),
        wage_capacity_weekly_eur=_cents_to_eur(row.wage_budget_cents),
        wage_room_weekly_eur=_cents_to_eur(max(0, row.transfer_budget_cents) / weeks_left(
            conn, meta.season_id, meta.current_date)),
        monthly=MonthlyOut(tv_eur=tv, commercial_eur=commercial, wages_eur=wages,
                           running_eur=running, profit_eur=tv + commercial + wages + running),
        season_profit_so_far_eur=_cents_to_eur(
            season_profit_cents(conn, club_id, meta.season_id)),
        changes=[ChangeOut(date=c.date, label=LABELS[c.kind],
                           before_eur=_cents_to_eur(c.before_cents),
                           after_eur=_cents_to_eur(c.after_cents))
                 for c in rate_changes(conn, world, club_id)],
        transactions=_transactions(conn, world, club_id),
        board_enabled=meta.board_enabled, board=board,
    )


def _transactions(conn: Connection, world: World, club_id: int) -> list[TransactionOut]:
    """The club's latest one-off money, labelled: a transfer with the player and the other club,
    prize money with the competition."""
    rows = conn.execute(text(
        "SELECT l.date, l.kind, l.amount_cents, c.name AS competition, t.from_club_id, "
        "t.to_club_id, fc.name AS from_club, tc.name AS to_club, pe.first_name, pe.last_name, "
        "pe.known_as FROM finance_ledger l "
        "LEFT JOIN competition c ON l.kind = 'prize' AND c.id = l.ref_id "
        "LEFT JOIN transfer t ON l.kind = 'transfer' AND t.id = l.ref_id "
        "LEFT JOIN club fc ON fc.id = t.from_club_id LEFT JOIN club tc ON tc.id = t.to_club_id "
        "LEFT JOIN person pe ON pe.id = t.player_id "
        "WHERE l.club_id = :club AND l.kind IN :kinds ORDER BY l.date DESC, l.id DESC LIMIT :n"
    ).bindparams(bindparam("kinds", expanding=True)),
        {"club": club_id, "kinds": list(ONE_OFF),
         "n": world.defs.finance.display.transactions_shown}).all()
    return [TransactionOut(date=r.date, kind=r.kind, label=_label(r, club_id),
                           amount_eur=_cents_to_eur(r.amount_cents)) for r in rows]


def _label(r: Row[Any], club_id: int) -> str:
    if r.kind == "prize" and r.competition:
        return f"{r.competition} prize money"
    if r.kind == "transfer" and r.first_name is not None:
        player = display_name(r.first_name, r.last_name, r.known_as)
        if r.to_club_id == club_id and r.from_club:
            return f"Signed {player} from {r.from_club}"
        if r.from_club_id == club_id and r.to_club:
            return f"Sold {player} to {r.to_club}"
    return LABELS.get(str(r.kind), str(r.kind))


def _season_label(conn: Connection, season_id: int) -> str:
    return str(conn.execute(text("SELECT label FROM season WHERE id = :s"),
                            {"s": season_id}).scalar_one())
