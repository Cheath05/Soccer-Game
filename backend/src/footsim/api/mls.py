"""MLS's roster rules for the roster page (W9a B3-B4; world/mls.py): where a club stands under
the rules, and the user's choices (a player's designation, the roster model, an international
slot bought for GAM). Amounts are euros a year (the client shows them in the user's currency);
``usd_per_euro`` is the rate MLS's dollar figures were converted at."""

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import Connection, text

from footsim.api.routes import Session, _not_simulating
from footsim.api.schemas import ClubRef
from footsim.world import mls
from footsim.world.context import World, get_world
from footsim.world.meta import CareerMeta, read_meta
from footsim.world.overall_history import player_overalls, primary_positions

router = APIRouter(prefix="/api/mls")


class ChargeOut(BaseModel):
    base_eur: int  # before allocation money
    tam_eur: int  # bought down with TAM
    gam_eur: int  # bought down with GAM
    charge_eur: int  # against the budget


class RosterPlayerOut(BaseModel):
    id: int
    name: str
    age: int
    position: str
    overall: int
    salary_eur: int  # a year, what the club pays him
    designation: str  # senior | supplemental | dp | u22 | homegrown | generation_adidas
    roster: str  # senior | supplemental
    international: bool
    canadian: bool
    homegrown: bool
    generation_adidas: bool
    loan: str | None  # "in" (here on loan) | "out" (lent out) | None
    charge: ChargeOut
    options: list[str]  # "designation:roster" pairs he may take


class AllocationOut(BaseModel):
    tam_eur: int  # this season's TAM
    tam_used_eur: int
    tam_left_eur: int
    gam_eur: int  # GAM held (Model 2's expiring part included)
    gam_expiring_eur: int
    gam_used_eur: int  # what the buy-downs take this season
    gam_left_eur: int


class SlotsOut(BaseModel):
    senior: int
    senior_slots: int
    supplemental: int
    supplemental_slots: int
    designated_players: int
    designated_slots: int
    u22: int
    u22_slots: int
    internationals: int
    international_slots: int


class RosterOut(BaseModel):
    club: ClubRef
    yours: bool
    season_id: int
    roster_model: int
    model_choosable: bool  # the user may still change it (before the first league match)
    usd_per_euro: float
    budget_eur: int
    budget_used_eur: int
    budget_left_eur: int
    max_charge_eur: int
    empty_senior_slots_charged: int
    allocation: AllocationOut
    slots: SlotsOut
    compliant: bool
    problems: list[str]
    adding_blocked: bool  # the user's club can't add players until it complies
    players: list[RosterPlayerOut]


class SlotSellerOut(BaseModel):
    club: ClubRef
    spare: int  # slots it could sell (beyond the one it keeps)


class SlotSellersOut(BaseModel):
    price_eur: int  # a slot's price in GAM
    gam_left_eur: int  # the user's GAM not taken by buy-downs
    sellers: list[SlotSellerOut]


class DesignationIn(BaseModel):
    player_id: int
    designation: str
    roster: str | None = None  # needed only for a Homegrown player (senior or supplemental)


class ModelIn(BaseModel):
    model: int


class SlotIn(BaseModel):
    from_club_id: int


def _eur(cents: int) -> int:
    return round(cents / 100)


def _roster(conn: Connection, world: World, meta: CareerMeta, club_id: int,
            day: date) -> RosterOut:
    if not mls.under_rules(conn, club_id, meta.season_id):
        raise HTTPException(404, "That club doesn't play under MLS's roster rules.")
    fig = mls.figures(world)
    report = mls.club_report(conn, world, meta, club_id, day, mls.money_for(world, meta))
    row = mls.state(conn, club_id, meta.season_id)
    assert row is not None
    ids = [m.player_id for m in report.members]
    overall = player_overalls(conn, world, ids)
    positions = primary_positions(conn, ids)
    name = str(conn.execute(text("SELECT name FROM club WHERE id = :c"), {"c": club_id}
                            ).scalar_one())
    dp_slots, u22_slots = fig.model(int(row.roster_model))
    played = int(conn.execute(text(
        "SELECT COUNT(*) FROM fixture f JOIN competition c ON c.id = f.competition_id "
        "WHERE c.key = :k AND f.season_id = :s AND f.stage = 'league' AND f.status = 'played' "
        "AND :c IN (f.home_club_id, f.away_club_id)"),
        {"k": world.defs.mls.league, "s": meta.season_id, "c": club_id}).scalar_one())
    gam = int(row.gam_cents) + int(row.gam_expiring_cents)
    players = []
    for m in report.members:
        charge = report.charges[m.player_id]
        options = [f"{p.designation}:{p.slot}" for p in mls.placements(fig, m)]
        players.append(RosterPlayerOut(
            id=m.player_id, name=m.name, age=m.age, position=positions.get(m.player_id, ""),
            overall=overall.get(m.player_id, 0), salary_eur=_eur(m.wage),
            designation=m.designation, roster=m.slot, international=m.international,
            canadian=m.canadian, homegrown=m.homegrown, generation_adidas=m.ga, loan=m.loan,
            charge=ChargeOut(base_eur=_eur(charge.base), tam_eur=_eur(charge.tam),
                             gam_eur=_eur(charge.gam), charge_eur=_eur(charge.charge)),
            options=options))
    players.sort(key=lambda p: (p.roster != "senior", -p.charge.charge_eur, -p.salary_eur, p.id))
    yours = club_id == meta.user_club_id
    return RosterOut(
        club=ClubRef(id=club_id, name=name), yours=yours, season_id=meta.season_id,
        roster_model=int(row.roster_model), model_choosable=yours and played == 0,
        usd_per_euro=fig.per_euro, budget_eur=_eur(report.budget),
        budget_used_eur=_eur(report.used), budget_left_eur=_eur(report.left),
        max_charge_eur=_eur(fig.max_charge), empty_senior_slots_charged=report.empty_slots,
        allocation=AllocationOut(
            tam_eur=_eur(int(row.tam_cents)), tam_used_eur=_eur(report.tam_used),
            tam_left_eur=_eur(int(row.tam_cents) - report.tam_used), gam_eur=_eur(gam),
            gam_expiring_eur=_eur(int(row.gam_expiring_cents)),
            gam_used_eur=_eur(report.gam_used), gam_left_eur=_eur(gam - report.gam_used)),
        slots=SlotsOut(
            senior=report.senior, senior_slots=world.defs.mls.senior_slots,
            supplemental=report.supplemental,
            supplemental_slots=world.defs.mls.supplemental_slots,
            designated_players=report.dps, designated_slots=dp_slots, u22=report.u22s,
            u22_slots=u22_slots, internationals=report.internationals,
            international_slots=int(row.international_slots)),
        compliant=report.compliant, problems=[p.text for p in report.problems],
        adding_blocked=yours and not report.compliant, players=players)


@router.get("/roster")
def roster(session: Session, club_id: int | None = None) -> RosterOut:
    """A club's roster under MLS's rules: the user's, or ``club_id``'s."""
    world = get_world()
    with session.read() as conn:
        meta = read_meta(conn)
        club = club_id if club_id is not None else meta.user_club_id
        if club is None:
            raise HTTPException(404, "Watching only: there's no club of your own.")
        return _roster(conn, world, meta, club, meta.current_date)


@router.get("/international-slot")
def international_slot_sellers(session: Session) -> SlotSellersOut:
    """The MLS clubs the user could buy an international slot from, most to spare first, and the
    price in GAM."""
    world = get_world()
    rules = world.defs.mls
    with session.read() as conn:
        meta = read_meta(conn)
        club_id = meta.user_club_id
        if club_id is None or not mls.under_rules(conn, club_id, meta.season_id):
            raise HTTPException(404, "Your club doesn't play under MLS's roster rules.")
        day = meta.current_date
        report = mls.club_report(conn, world, meta, club_id, day, mls.money_for(world, meta))
        row = mls.state(conn, club_id, meta.season_id)
        assert row is not None
        gam = int(row.gam_cents) + int(row.gam_expiring_cents) - report.gam_used
        sellers = []
        for other in sorted(mls.mls_club_ids(conn, world, meta.season_id) - {club_id}):
            state = mls.state(conn, other, meta.season_id)
            if state is None:
                continue
            members, _ = mls.load_members(conn, world, meta, other, day)
            spare = (int(state.international_slots) - sum(1 for m in members if m.international)
                     - rules.ai.spare_slots_kept)
            if spare > 0:
                name = str(conn.execute(text("SELECT name FROM club WHERE id = :c"),
                                        {"c": other}).scalar_one())
                sellers.append(SlotSellerOut(club=ClubRef(id=other, name=name), spare=spare))
        sellers.sort(key=lambda s: (-s.spare, s.club.name))
        return SlotSellersOut(price_eur=_eur(mls.figures(world).c(rules.slot_price_gam)),
                              gam_left_eur=_eur(gam), sellers=sellers)


def _act(session: Session, body: DesignationIn | ModelIn | SlotIn) -> RosterOut:
    _not_simulating(session)
    world = get_world()
    with session.write() as conn:
        meta = read_meta(conn)
        day = meta.current_date
        try:
            if isinstance(body, DesignationIn):
                mls.set_designation(conn, world, meta, day, body.player_id, body.designation,
                                    body.roster)
            elif isinstance(body, ModelIn):
                mls.set_roster_model(conn, world, meta, day, body.model)
            else:
                mls.buy_international_slot(conn, world, meta, day, body.from_club_id)
        except mls.RosterRefused as exc:
            raise HTTPException(409, str(exc)) from exc
        assert meta.user_club_id is not None
        result = _roster(conn, world, meta, meta.user_club_id, day)
    session.autosave()
    return result


@router.put("/designation")
def put_designation(body: DesignationIn, session: Session) -> RosterOut:
    """Designate one of the user's players: dp, u22, senior (a TAM buy-down for a player paid
    above the maximum), homegrown (with ``roster``), supplemental, generation_adidas. 409 with
    the rule that blocks it."""
    return _act(session, body)


@router.put("/roster-model")
def put_roster_model(body: ModelIn, session: Session) -> RosterOut:
    """The user's roster model (1 or 2), before their club's first league match."""
    return _act(session, body)


@router.post("/international-slot")
def post_international_slot(body: SlotIn, session: Session) -> RosterOut:
    """Buy an international slot for the season from an MLS club with one to spare, for GAM."""
    return _act(session, body)
