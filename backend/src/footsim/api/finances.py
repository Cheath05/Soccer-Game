"""The user's club's finances page (W3-3): the balance, budgets, this season's money by kind,
the latest ledger rows and the board's view. Read from ``club_finance`` and ``finance_ledger``
(world/finance.py), never recomputed here."""

from sqlalchemy import Connection, select, text

from footsim.api.schemas import BoardOut, ClubRef, FinanceLineOut, FinancesOut, LedgerRowOut
from footsim.persistence.schema import club, club_finance
from footsim.world.context import World
from footsim.world.finance import club_leagues, projected_revenue_cents, wage_bills
from footsim.world.meta import read_meta
from footsim.world.season import standings

LABELS = {
    "opening": "Opening balance",
    "broadcast": "League TV money",
    "club_income": "Commercial and matchday",
    "wages": "Wages",
    "operating": "Running costs",
    "month": "Month's net",
    "prize": "League prize money",
    "parachute": "Parachute payment",
    "transfer": "Transfers",
    "adjustment": "Owner investment",
}
RECENT_ROWS = 20

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
    by_kind = conn.execute(text(
        "SELECT kind, SUM(amount_cents) AS total FROM finance_ledger "
        "WHERE club_id = :club AND season_id = :season AND kind != 'opening' GROUP BY kind"),
        {"club": club_id, "season": meta.season_id}).all()
    lines = [FinanceLineOut(kind=r.kind, label=LABELS.get(r.kind, r.kind),
                            amount_eur=_cents_to_eur(int(r.total))) for r in by_kind]
    income = sorted((x for x in lines if x.amount_eur > 0), key=lambda x: -x.amount_eur)
    expenses = sorted((x for x in lines if x.amount_eur < 0), key=lambda x: x.amount_eur)
    recent = [LedgerRowOut(date=r.date, kind=r.kind, label=LABELS.get(r.kind, r.kind),
                           amount_eur=_cents_to_eur(r.amount_cents))
              for r in conn.execute(text(
                  "SELECT date, kind, amount_cents FROM finance_ledger WHERE club_id = :club "
                  "ORDER BY date DESC, id DESC LIMIT :n"), {"club": club_id, "n": RECENT_ROWS})]
    position, played, size = None, 0, None
    if league is not None:
        table = standings(conn, world, meta, league[1], meta.season_id)
        size = len(table)
        mine = next((r for r in table if r.club_id == club_id), None)
        if mine is not None and mine.played:
            position, played = mine.position, mine.played
    return FinancesOut(
        club=ClubRef(id=club_id, name=name), season=_season_label(conn, meta.season_id),
        league=world.defs.leagues[key].name if key else None,
        balance_eur=_cents_to_eur(row.balance_cents),
        transfer_budget_eur=_cents_to_eur(row.transfer_budget_cents),
        wage_budget_weekly_eur=_cents_to_eur(row.wage_budget_cents),
        wage_bill_weekly_eur=_cents_to_eur(wage_bills(conn).get(club_id, 0)),
        projected_revenue_eur=_cents_to_eur(
            projected_revenue_cents(world, key, row.club_income_cents)),
        income=income, expenses=expenses, net_eur=sum(x.amount_eur for x in lines),
        recent=recent,
        board=BoardOut(target=row.board_target, position=position, played=played,
                       league_size=size, confidence=row.board_confidence,
                       mood=mood(row.board_confidence)),
    )


def _season_label(conn: Connection, season_id: int) -> str:
    return str(conn.execute(text("SELECT label FROM season WHERE id = :s"),
                            {"s": season_id}).scalar_one())
