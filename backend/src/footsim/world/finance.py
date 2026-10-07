"""Club finances (W3; docs/plans/w3-w4-finances-transfers.md, data/config/finance/finance.yaml).

A club's balance is its cash, and always equals the sum of its ledger: every change to it is
posted with a ledger row (``post``). Its own income (commercial and matchday) is derived once,
from its wage bill, when its finances begin; league income comes on top, by the league it plays
in each season. The budgets are set at each season's start, and the board's expectation with
them. Nothing here is random.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

import numpy as np
from sqlalchemy import Connection, select, text

from footsim.persistence.schema import club, club_finance, finance_ledger
from footsim.world.context import World
from footsim.world.meta import CareerMeta
from footsim.world.overall_history import player_overalls

SQUAD_STRENGTH_PLAYERS = 16  # a squad's strength: the mean overall of its best this many
KINDS = frozenset({"opening", "broadcast", "club_income", "wages", "operating", "month", "prize",
                   "parachute", "transfer", "adjustment"})


@dataclass(frozen=True)
class Entry:
    """One change to a club's balance."""

    club_id: int
    kind: str  # one of KINDS
    amount_cents: int
    ref_id: int | None = None


def post(conn: Connection, day: date, season_id: int, entries: Iterable[Entry]) -> None:
    """Write ``entries`` to the ledger and move the balances with them, together. Every club
    must have finances, and every kind be known: a row that moved no balance would break the
    ledger."""
    rows = [e for e in entries if e.amount_cents != 0]
    if not rows:
        return
    unknown_kinds = {e.kind for e in rows} - KINDS
    if unknown_kinds:
        raise ValueError(f"unknown ledger kinds {sorted(unknown_kinds)}")
    clubs = {e.club_id for e in rows}
    found = {int(r.club_id) for r in conn.execute(
        select(club_finance.c.club_id).where(club_finance.c.club_id.in_(sorted(clubs))))}
    if found != clubs:
        raise ValueError(f"no finances for clubs {sorted(clubs - found)}")
    conn.execute(finance_ledger.insert(), [
        {"club_id": e.club_id, "date": day.isoformat(), "season_id": season_id, "kind": e.kind,
         "amount_cents": e.amount_cents, "ref_id": e.ref_id} for e in rows])
    totals: dict[int, int] = defaultdict(int)
    for e in rows:
        totals[e.club_id] += e.amount_cents
    conn.execute(text("UPDATE club_finance SET balance_cents = balance_cents + :amount "
                      "WHERE club_id = :club"),
                 [{"club": c, "amount": a} for c, a in sorted(totals.items())])


def wage_bills(conn: Connection) -> dict[int, int]:
    """Each club's weekly wage bill in cents: its active contracts."""
    rows = conn.execute(text("SELECT club_id, SUM(wage_weekly_cents) AS bill FROM contract "
                             "WHERE is_active = 1 GROUP BY club_id"))
    return {int(r.club_id): int(r.bill) for r in rows}


def club_leagues(conn: Connection, season_id: int) -> dict[int, tuple[str, int]]:
    """The league each club plays in a season: (competition key, competition id)."""
    rows = conn.execute(text(
        "SELECT m.club_id, c.key, c.id FROM club_league_membership m "
        "JOIN competition c ON c.id = m.competition_id WHERE m.season_id = :season"),
        {"season": season_id})
    return {int(r.club_id): (str(r.key), int(r.id)) for r in rows}


def projected_revenue_cents(world: World, league_key: str | None, club_income_cents: int) -> int:
    """A season's revenue as a club plans it: its own income and a mid-table share of its
    league's."""
    league = world.defs.finance.league_income.get(league_key) if league_key else None
    return club_income_cents + (round(league.expected * 100) if league else 0)


def initialize_finances(conn: Connection, world: World, meta: CareerMeta, day: date) -> None:
    """Every club without finances gets them, as if they began on ``day``: its own income from
    its wage bill (a club's size is already in what it pays its players), an opening balance,
    and the budgets and the board's expectation for the current season."""
    rules = world.defs.finance
    existing = {int(r.club_id) for r in conn.execute(select(club_finance.c.club_id))}
    bills = wage_bills(conn)
    leagues = club_leagues(conn, meta.season_id)
    new_rows, opening = [], []
    for (club_id,) in conn.execute(select(club.c.id).order_by(club.c.id)):
        if club_id in existing:
            continue
        key = leagues[club_id][0] if club_id in leagues else None
        league = rules.league_income.get(key) if key else None
        expected = league.expected * 100 if league else 0.0
        own = bills.get(club_id, 0) * 52 / rules.wage_ratio_start - expected
        club_income = round(max(own, rules.club_income_floor * expected, 0.0))
        revenue = projected_revenue_cents(world, key, club_income)
        new_rows.append({"club_id": club_id, "balance_cents": 0, "club_income_cents": club_income,
                         "transfer_budget_cents": 0, "wage_budget_cents": 0,
                         "budget_season_id": meta.season_id, "board_target": None,
                         "board_confidence": rules.board.confidence_start,
                         "settled_on": day.isoformat()})  # the month begun is in the opening
        opening.append(Entry(club_id, "opening", round(rules.starting_cash * revenue)))
    if not new_rows:
        return
    conn.execute(club_finance.insert(), new_rows)
    post(conn, day, meta.season_id, opening)
    set_budgets(conn, world, meta.season_id, {r["club_id"] for r in new_rows})


def set_budgets(conn: Connection, world: World, season_id: int,
                clubs: set[int] | None = None) -> None:
    """The board's budgets for a season (every club, or just ``clubs``): wages up to a share of
    the season's projected revenue, and a transfer budget from the revenue and the cash in hand
    (none while in debt). The board expects each club to finish where its squad ranks in its
    league."""
    rules = world.defs.finance
    leagues = club_leagues(conn, season_id)
    targets = board_targets(conn, world, leagues)
    rows = conn.execute(select(club_finance)).all()
    updates = []
    for r in rows:
        if clubs is not None and r.club_id not in clubs:
            continue
        key = leagues[r.club_id][0] if r.club_id in leagues else None
        revenue = projected_revenue_cents(world, key, r.club_income_cents)
        transfer = (round(revenue * rules.budget_share + r.balance_cents * rules.cash_share)
                    if r.balance_cents >= 0 else 0)
        updates.append({"club": r.club_id, "transfer": transfer,
                        "wage": round(revenue * rules.wage_budget_ratio / 52),
                        "season": season_id, "target": targets.get(r.club_id)})
    if updates:
        conn.execute(text(
            "UPDATE club_finance SET transfer_budget_cents = :transfer, wage_budget_cents = :wage, "
            "budget_season_id = :season, board_target = :target WHERE club_id = :club"), updates)


def squad_strengths(conn: Connection, world: World) -> dict[int, float]:
    """Each club's squad strength: the mean overall of its best ``SQUAD_STRENGTH_PLAYERS``."""
    overalls = player_overalls(conn, world)
    by_club: dict[int, list[int]] = defaultdict(list)
    for r in conn.execute(text("SELECT person_id, club_id FROM contract WHERE is_active = 1")):
        if r.person_id in overalls:
            by_club[int(r.club_id)].append(overalls[r.person_id])
    return {c: float(np.mean(sorted(v, reverse=True)[:SQUAD_STRENGTH_PLAYERS]))
            for c, v in by_club.items()}


def board_targets(conn: Connection, world: World,
                  leagues: dict[int, tuple[str, int]]) -> dict[int, int]:
    """The league position the board expects of each club in a league: where its squad ranks
    there (the strongest squad is expected to win it)."""
    strengths = squad_strengths(conn, world)
    by_league: dict[int, list[int]] = defaultdict(list)
    for club_id, (_, competition_id) in leagues.items():
        by_league[competition_id].append(club_id)
    targets = {}
    for clubs in by_league.values():
        ranked = sorted(clubs, key=lambda c: (-strengths.get(c, 0.0), c))
        targets.update({c: rank for rank, c in enumerate(ranked, start=1)})
    return targets


def ledger_mismatches(conn: Connection) -> list[int]:
    """Clubs whose balance isn't the sum of their ledger (there should be none)."""
    rows = conn.execute(text(
        "SELECT f.club_id FROM club_finance f LEFT JOIN (SELECT club_id, SUM(amount_cents) AS s "
        "FROM finance_ledger GROUP BY club_id) l ON l.club_id = f.club_id "
        "WHERE f.balance_cents != COALESCE(l.s, 0)"))
    return [int(r.club_id) for r in rows]
