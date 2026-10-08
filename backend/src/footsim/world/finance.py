"""Club finances (W3; docs/plans/w3-w4-finances-transfers.md, data/config/finance/finance.yaml).

A club's balance is its cash, and always equals the sum of its ledger: every change to it is
posted with a ledger row (``post``). Its own income (commercial and matchday) is derived once,
from its wage bill, when its finances begin; league income comes on top, by the league it plays
in each season.

Two kinds of money move a balance. Recurring money (TV money, commercial and matchday, wages,
running costs) is settled each month (``settle_month``) and shown as the month's profit
(``monthly_parts``). One-off money (the opening balance, transfers, prizes, parachutes, the
owner's investment) is a transaction.

A club has one budget: what it may commit in a season to transfer fees and new wages (a signing
costs its fee and its weekly wage for the weeks left in the season: ``signing_cost_cents``). It
is set at each season's start (``set_budgets``), from the club's revenue and cash, less any
wages it pays beyond its capacity, and the transfers of the season move it. The user may turn
their board off (``set_board_enabled``): their budget is then all of their cash. Nothing here
is random.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

import numpy as np
from sqlalchemy import Connection, bindparam, or_, select, text, update

from footsim.persistence.schema import club, club_finance, finance_ledger
from footsim.persistence.schema import season as season_table
from footsim.world.context import World
from footsim.world.meta import CareerMeta, write_meta
from footsim.world.overall_history import player_overalls

SQUAD_STRENGTH_PLAYERS = 16  # a squad's strength: the mean overall of its best this many
KINDS = frozenset({"opening", "broadcast", "club_income", "wages", "operating", "month", "prize",
                   "parachute", "transfer", "adjustment"})
RECURRING = ("broadcast", "club_income", "wages", "operating")  # a month's parts, in this order
ONE_OFF = ("opening", "transfer", "prize", "parachute", "adjustment")  # the transactions


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
    """Each club's weekly wage bill in cents: its active contracts (its loans in included), less
    the share a borrowing club pays for each of its players out on loan, so every euro of a wage
    is paid once (W4-8)."""
    rows = conn.execute(text(
        "SELECT club_id, SUM(w) AS bill FROM ("
        "  SELECT club_id, wage_weekly_cents AS w FROM contract WHERE is_active = 1"
        "  UNION ALL"
        "  SELECT o.club_id, -l.wage_weekly_cents FROM contract l JOIN contract o"
        "    ON o.person_id = l.person_id AND o.is_active = 1 AND o.kind != 'loan'"
        "  WHERE l.is_active = 1 AND l.kind = 'loan'"
        ") GROUP BY club_id"))
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


@dataclass(frozen=True)
class MonthlyParts:
    """A club's month of recurring money, in cents: income is positive and costs negative."""

    broadcast: int  # its equal share of its league's TV money
    club_income: int  # commercial and matchday
    wages: int
    operating: int  # running costs

    @property
    def profit(self) -> int:
        return self.broadcast + self.club_income + self.wages + self.operating


def monthly_parts(world: World, league_key: str | None, club_income_cents: int,
                  weekly_bill_cents: int) -> MonthlyParts:
    """A club's month of recurring money at today's rates: the league it plays in, its own
    income and its wage bill. Merit comes when the league ends, not here. ``settle_month`` books
    these same figures, and the finances page shows them as the month's profit."""
    rules = world.defs.finance
    league = rules.league_income.get(league_key) if league_key else None
    revenue = projected_revenue_cents(world, league_key, club_income_cents)
    return MonthlyParts(
        broadcast=round(league.base * 100 / 12) if league else 0,
        club_income=round(club_income_cents / 12),
        wages=-round(weekly_bill_cents * 52 / 12),
        operating=-round(rules.operating_costs * revenue / 12))


def weeks_left(conn: Connection, season_id: int, day: date) -> float:
    """The weeks of season ``season_id`` left on ``day`` (at least 1): what a new wage is charged
    for, as the club pays it for the rest of the season."""
    end: str = conn.execute(select(season_table.c.end_date).where(season_table.c.id == season_id)
                            ).scalar_one()
    return max(1.0, (date.fromisoformat(end) - day).days / 7)


def signing_cost_cents(fee_cents: int, wage_weekly_cents: int, weeks: float) -> int:
    """What signing a player takes from a budget: his fee and his new wage for the weeks left in
    the season (``weeks_left``)."""
    return fee_cents + round(wage_weekly_cents * weeks)


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
        club_income = _own_income(world, key, bills.get(club_id, 0))
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
    set_budgets(conn, world, meta, {r["club_id"] for r in new_rows})


def _own_income(world: World, league_key: str | None, weekly_bill_cents: int) -> int:
    """A club's own yearly income (commercial and matchday): what its wage bill says it earns,
    less the league income it gets anyway (a club's size is already in what it pays)."""
    rules = world.defs.finance
    league = rules.league_income.get(league_key) if league_key else None
    expected = league.expected * 100 if league else 0.0
    own = weekly_bill_cents * 52 / rules.wage_ratio_start - expected
    return round(max(own, rules.club_income_floor * expected, 0.0))


def settle_month(conn: Connection, world: World, meta: CareerMeta, day: date,
                 positions: dict[int, tuple[int, int]]) -> None:
    """The first of each month, once: every club's month of league income (its equal share;
    merit comes when the league ends), its own income, its wages and its running costs. The
    user's club gets them itemised for its finances page, every other club one net row, which
    keeps a long career's save small. Then the board's confidence moves with the league table
    (``positions``: club -> (position, league matches played)).

    Finances begin settled on their first day (the opening balance covers that month), so a
    career that starts on 1 July has 11 settlements in its first season and 12 after."""
    due_clause = or_(club_finance.c.settled_on.is_(None),
                     club_finance.c.settled_on < day.isoformat())
    due = conn.execute(select(club_finance).where(due_clause).order_by(club_finance.c.club_id)
                       ).all()
    if not due:
        return
    bills = wage_bills(conn)
    leagues = club_leagues(conn, meta.season_id)
    entries = []
    for r in due:
        key = leagues[r.club_id][0] if r.club_id in leagues else None
        parts = monthly_parts(world, key, r.club_income_cents, bills.get(r.club_id, 0))
        if r.club_id == meta.user_club_id:
            entries += [Entry(r.club_id, "broadcast", parts.broadcast),
                        Entry(r.club_id, "club_income", parts.club_income),
                        Entry(r.club_id, "wages", parts.wages),
                        Entry(r.club_id, "operating", parts.operating)]
        else:
            entries.append(Entry(r.club_id, "month", parts.profit))
    post(conn, day, meta.season_id, entries)
    conn.execute(update(club_finance).where(due_clause).values(settled_on=day.isoformat()))
    _move_confidence(conn, world, positions)


def _move_confidence(conn: Connection, world: World,
                     positions: dict[int, tuple[int, int]]) -> None:
    """The board's confidence after a month: up while the club is above its target, down while
    below, once it has played a few league matches."""
    rules = world.defs.finance.board
    updates = []
    for r in conn.execute(select(club_finance.c.club_id, club_finance.c.board_target,
                                 club_finance.c.board_confidence)):
        if r.board_target is None or r.board_confidence is None or r.club_id not in positions:
            continue
        position, played = positions[r.club_id]
        if played < rules.min_played:
            continue
        step = max(-rules.max_step,
                   min(rules.max_step, (r.board_target - position) * rules.per_place))
        updates.append({"club": r.club_id,
                        "confidence": round(max(0.0, min(100.0, r.board_confidence + step)))})
    if updates:
        conn.execute(text("UPDATE club_finance SET board_confidence = :confidence "
                          "WHERE club_id = :club"), updates)


def _halfway(confidence: int | None, start: int) -> int:
    """Halfway back to ``start``, rounding towards it (so it always gets there in the end)."""
    if confidence is None:
        return start
    return start + int((confidence - start) / 2)


def pay_merit(conn: Connection, world: World, meta: CareerMeta, league_key: str,
              competition_id: int, finishers: list[tuple[int, int]], day: date) -> None:
    """A league's merit payments when it ends, by final position (``finishers``: (position,
    club)): the full merit for the champion, falling linearly to none for the last club."""
    league = world.defs.finance.league_income.get(league_key)
    if league is None or not finishers:
        return
    size = len(finishers)
    post(conn, day, meta.season_id, [
        Entry(club_id, "prize", round((league.for_position(position, size) - league.base) * 100),
              competition_id) for position, club_id in sorted(finishers)])


def start_season_finances(conn: Connection, world: World, meta: CareerMeta, old_season: int,
                          day: date) -> None:
    """A new season's money, once promotion and relegation are done (``meta.season_id`` is the
    new season):
    - a club that dropped to a poorer league gets a share of the league income it lost, once;
    - a club playing in a league for the first time (one the save has just started) has its own
      income worked out again, so it doesn't count its new league income twice;
    - the board's confidence goes halfway back to neutral;
    - every club's budget, wage capacity and the board's target are set for the season (after
      the parachute, so the cash it brings counts)."""
    rules = world.defs.finance
    before = club_leagues(conn, old_season)
    after = club_leagues(conn, meta.season_id)
    parachutes = []
    for club_id, (old_key, _) in sorted(before.items()):
        old_income = rules.league_income.get(old_key)
        new_key = after[club_id][0] if club_id in after else None
        new_income = rules.league_income.get(new_key) if new_key else None
        lost = ((old_income.expected if old_income else 0.0)
                - (new_income.expected if new_income else 0.0))
        if lost > 0:
            parachutes.append(Entry(club_id, "parachute", round(rules.parachute * lost * 100)))
    post(conn, day, meta.season_id, parachutes)
    newcomers = sorted(set(after) - set(before))
    if newcomers:
        bills = wage_bills(conn)
        conn.execute(text("UPDATE club_finance SET club_income_cents = :income "
                          "WHERE club_id = :club"),
                     [{"club": c, "income": _own_income(world, after[c][0], bills.get(c, 0))}
                      for c in newcomers])
    start = rules.board.confidence_start
    conn.execute(text("UPDATE club_finance SET board_confidence = :confidence "
                      "WHERE club_id = :club"),
                 [{"club": r.club_id, "confidence": _halfway(r.board_confidence, start)}
                  for r in conn.execute(select(club_finance.c.club_id,
                                               club_finance.c.board_confidence))])
    set_budgets(conn, world, meta)


def has_board(meta: CareerMeta, club_id: int) -> bool:
    """Every club has a board, but the user's when the user has turned it off."""
    return meta.board_enabled or club_id != meta.user_club_id


def wage_capacity_cents(world: World, revenue_cents: int) -> int:
    """The weekly wage bill a club's revenue supports (its wage capacity). It is shown, and the
    AI keeps to it; what a club pays above it comes out of its next budget."""
    return round(revenue_cents * world.defs.finance.wage_budget_ratio / 52)


def club_budget_cents(world: World, meta: CareerMeta, club_id: int, revenue_cents: int,
                      balance_cents: int, weekly_bill_cents: int) -> int:
    """A club's budget for fees and new wages in a season.
    - With a board (every AI club, and the user's unless they turned it off): a share of the
      season's revenue and a share of the cash in hand, less a year of the wages the club pays
      above its capacity (what it already pays beyond its means comes out of the budget first).
      None while in debt.
    - Without one (the user's choice): all of the club's cash."""
    if not has_board(meta, club_id):
        return max(0, balance_cents)
    if balance_cents < 0:
        return 0
    rules = world.defs.finance
    plan = round(revenue_cents * rules.budget_share + balance_cents * rules.cash_share)
    over = max(0, weekly_bill_cents - wage_capacity_cents(world, revenue_cents))
    return max(0, plan - over * 52)


def set_budgets(conn: Connection, world: World, meta: CareerMeta,
                clubs: set[int] | None = None) -> None:
    """The budgets for season ``meta.season_id`` (every club, or just ``clubs``): each club's
    budget for fees and new wages (``club_budget_cents``) and its wage capacity, with the board's
    target. The board expects each club to finish where its squad ranks in its league."""
    leagues = club_leagues(conn, meta.season_id)
    targets = board_targets(conn, world, leagues)
    bills = wage_bills(conn)
    updates = []
    for r in conn.execute(select(club_finance)).all():
        if clubs is not None and r.club_id not in clubs:
            continue
        key = leagues[r.club_id][0] if r.club_id in leagues else None
        revenue = projected_revenue_cents(world, key, r.club_income_cents)
        updates.append({
            "club": r.club_id, "season": meta.season_id, "target": targets.get(r.club_id),
            "budget": club_budget_cents(world, meta, r.club_id, revenue, r.balance_cents,
                                        bills.get(r.club_id, 0)),
            "wage": wage_capacity_cents(world, revenue)})
    if updates:
        conn.execute(text(
            "UPDATE club_finance SET transfer_budget_cents = :budget, wage_budget_cents = :wage, "
            "budget_season_id = :season, board_target = :target WHERE club_id = :club"), updates)


def set_board_enabled(conn: Connection, world: World, meta: CareerMeta, enabled: bool) -> None:
    """Turn the user's board on or off. The user's budget is worked out again at once: all their
    cash without a board, the board's plan with one. Nothing happens if the board is already as
    asked (so switching it back and forth isn't a way to refill a budget that has been spent).
    The board's target and confidence are kept either way, for when it comes back."""
    club_id = meta.user_club_id
    if club_id is None:
        raise ValueError("a watch-only career has no board")
    if enabled == meta.board_enabled:
        return
    meta.board_enabled = enabled
    write_meta(conn, meta)
    row = conn.execute(select(club_finance).where(club_finance.c.club_id == club_id)).one()
    league = club_leagues(conn, meta.season_id).get(club_id)
    revenue = projected_revenue_cents(world, league[0] if league else None,
                                      row.club_income_cents)
    conn.execute(update(club_finance).where(club_finance.c.club_id == club_id).values(
        transfer_budget_cents=club_budget_cents(world, meta, club_id, revenue, row.balance_cents,
                                                wage_bills(conn).get(club_id, 0))))


def set_sandbox_budget(conn: Connection, meta: CareerMeta, club_id: int,
                       budget_cents: int) -> None:
    """The sandbox: a new career's club starts with this budget to spend on fees and wages. When
    the club's cash doesn't cover it, the owner puts in the rest (an ``adjustment``), so the
    money is really there; a smaller budget only lowers the board's."""
    balance = int(conn.execute(select(club_finance.c.balance_cents)
                               .where(club_finance.c.club_id == club_id)).scalar_one())
    post(conn, meta.current_date, meta.season_id,
         [Entry(club_id, "adjustment", max(0, budget_cents - balance))])
    conn.execute(update(club_finance).where(club_finance.c.club_id == club_id)
                 .values(transfer_budget_cents=budget_cents))


@dataclass(frozen=True)
class RateChange:
    """A part of a club's month that moved between two settlements: cents a month, signed as in
    the ledger (a cost is negative). ``date`` is the settlement it first showed in."""

    date: str
    kind: str  # one of RECURRING
    before_cents: int
    after_cents: int


def rate_changes(conn: Connection, world: World, club_id: int) -> list[RateChange]:
    """The notable changes in a club's month, read from its itemised settlements (the user's
    club has them): a part is listed when it moved from one settlement to the next by at least
    ``display.change_share`` of what it was and ``display.change_amount``. The latest first.
    Relegation, say, shows once as a fall in TV money, not as a month after month of smaller
    payments."""
    rules = world.defs.finance.display
    months: dict[str, dict[str, int]] = defaultdict(dict)
    for r in conn.execute(text(
            "SELECT date, kind, SUM(amount_cents) AS amount FROM finance_ledger "
            "WHERE club_id = :club AND kind IN :kinds GROUP BY date, kind ORDER BY date"
    ).bindparams(bindparam("kinds", expanding=True)), {"club": club_id, "kinds": list(RECURRING)}):
        months[r.date][r.kind] = int(r.amount)
    min_amount = round(rules.change_amount * 100)
    found: list[RateChange] = []
    days = sorted(months)
    for earlier, later in zip(days, days[1:], strict=False):
        for kind in RECURRING:
            before, after = months[earlier].get(kind, 0), months[later].get(kind, 0)
            moved = abs(after - before)
            if moved >= min_amount and moved >= rules.change_share * abs(before):
                found.append(RateChange(later, kind, before, after))
    found.sort(key=lambda c: c.date, reverse=True)  # stable: a day's parts keep their order
    return found[:rules.changes_shown]


def season_profit_cents(conn: Connection, club_id: int, season_id: int) -> int:
    """A club's recurring money settled so far in a season: its months' profits. One-off money
    (transfers, prizes, parachutes) isn't profit."""
    return int(conn.execute(text(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM finance_ledger WHERE club_id = :club "
        "AND season_id = :season AND kind IN :kinds").bindparams(
            bindparam("kinds", expanding=True)),
        {"club": club_id, "season": season_id, "kinds": [*RECURRING, "month"]}).scalar_one())


def squad_strengths(conn: Connection, world: World) -> dict[int, float]:
    """Each club's squad strength: the mean overall of its best ``SQUAD_STRENGTH_PLAYERS``."""
    overalls = player_overalls(conn, world)
    by_club: dict[int, list[int]] = defaultdict(list)
    for r in conn.execute(text("SELECT person_id, club_id FROM playing")):
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
