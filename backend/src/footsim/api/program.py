"""The NCAA program builder mode for a college coach (W9d, world/college/program.py): the
program's money, its facilities and its crowds; the class budget; upgrades; turning the mode on."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Connection

from footsim.api.routes import Session, _not_simulating
from footsim.defs.college import on
from footsim.world.college import program as pg
from footsim.world.college.common import is_college_club
from footsim.world.college.recruiting import along, load_programs, season_start
from footsim.world.context import World, get_world
from footsim.world.meta import CareerMeta, read_meta, write_meta

router = APIRouter(prefix="/api")


class LineOut(BaseModel):
    kind: str  # allocation | tickets | boosters | boosters_ncaa | ncaa | scholarships | ...
    amount_eur: int


class FacilityOut(BaseModel):
    kind: str  # training | stadium
    level: int
    effect: str  # what this level does, in words
    next_effect: str | None
    next_cost_eur: int | None  # None at the top level
    upkeep_eur: int  # a season, at this level
    building_to: int | None
    ready_season: str | None  # the season label it's ready for


class CrowdOut(BaseModel):
    fixture_id: int
    date: str
    opponent: str
    attendance: int


class ProgramOut(BaseModel):
    mode: str  # classic | builder
    balance_eur: int
    season: list[LineOut]  # this season's money so far, by kind
    class_budget: float  # full scholarships for next season's class
    class_committed: float  # already committed or signed in it
    class_affordable: float  # the most the program can set aside
    scholarship_eur: int  # a full scholarship's cost a year
    next_allocation_eur: int
    build_cutoff: str  # work ordered before this day is ready next season
    facilities: list[FacilityOut]
    capacity: int
    crowds: list[CrowdOut]


class BudgetIn(BaseModel):
    budget: float = Field(ge=0, le=40)


class ModeIn(BaseModel):
    mode: str


def _eur(world: World, dollars: float) -> int:
    return pg.cents(world, dollars) // 100


def _label(conn: Connection, meta: CareerMeta, season_id: int) -> str:
    start = season_start(conn, meta.season_id).year + (season_id - meta.season_id)
    return f"{start}-{str(start + 1)[2:]}"


def _effect(world: World, kind: str, level: int) -> str:
    cfg = pg.rules(world).facilities
    if kind == "training":
        growth = (cfg.training.growth or [0.0] * 5)[level - 1]
        return (f"Players grow {round(growth * 100)}% faster" if growth
                else "Players grow at the normal rate")
    capacity = (cfg.stadium.capacity or [0] * 5)[level - 1]
    price = pg.rules(world).tickets.price[level]
    return f"{capacity:,} seats, ${price:g} tickets"


def _program(conn: Connection, world: World, meta: CareerMeta) -> ProgramOut:
    user = meta.user_club_id
    if user is None or not is_college_club(conn, user):
        raise HTTPException(404, "The program is for a college coach.")
    cfg = pg.rules(world)
    if not pg.is_on(conn):
        return ProgramOut(mode=meta.college_mode, balance_eur=0, season=[], class_budget=0,
                          class_committed=0, class_affordable=0, scholarship_eur=0,
                          next_allocation_eur=0, build_cutoff="", facilities=[], capacity=0,
                          crowds=[])
    p = load_programs(conn, world, meta.season_id + 1)[user]
    found = pg.facilities(conn)[user]
    facilities = []
    for kind in ("training", "stadium"):
        f = found[kind]
        spec = cfg.facilities.of(kind)
        top = f.level >= 5
        facilities.append(FacilityOut(
            kind=kind, level=f.level, effect=_effect(world, kind, f.level),
            next_effect=None if top else _effect(world, kind, f.level + 1),
            next_cost_eur=None if top else _eur(world, spec.cost[f.level]),
            upkeep_eur=_eur(world, spec.upkeep[f.level - 1]), building_to=f.building_to,
            ready_season=_label(conn, meta, f.ready_season) if f.ready_season else None))
    return ProgramOut(
        mode=meta.college_mode, balance_eur=pg.balance_of(conn, user) // 100,
        season=[LineOut(kind=line.kind, amount_eur=line.amount_cents // 100)
                for line in pg.season_lines(conn, user, meta.season_id)],
        class_budget=round(pg.class_budgets(conn).get(user, 0.0), 2),
        class_committed=round(p.class_money, 2),
        class_affordable=round(pg.affordable_class(conn, world, user, meta.season_id), 2),
        scholarship_eur=_eur(world, cfg.costs.scholarship),
        next_allocation_eur=_eur(world, along(cfg.allocation, p.prestige)),
        build_cutoff=on(cfg.facilities.build_cutoff,
                        season_start(conn, meta.season_id)).isoformat(),
        facilities=facilities,
        capacity=(cfg.facilities.stadium.capacity or [0] * 5)[found["stadium"].level - 1],
        crowds=[CrowdOut(fixture_id=int(r.id), date=str(r.date), opponent=str(r.opponent),
                         attendance=int(r.attendance))
                for r in pg.home_crowds(conn, user, meta.season_id)])


@router.get("/program")
def get_program(session: Session) -> ProgramOut:
    with session.read() as conn:
        return _program(conn, get_world(), read_meta(conn))


@router.put("/program/class-budget")
def put_class_budget(body: BudgetIn, session: Session) -> ProgramOut:
    _not_simulating(session)
    world = get_world()
    with session.write() as conn:
        meta = read_meta(conn)
        _program(conn, world, meta)  # a college coach's, in the mode
        try:
            pg.set_class_budget(conn, world, meta, meta.user_club_id or 0, body.budget)
        except pg.ProgramError as exc:
            raise HTTPException(409, str(exc)) from exc
    session.autosave()
    return get_program(session)


@router.post("/program/upgrade/{kind}")
def post_upgrade(kind: str, session: Session) -> ProgramOut:
    _not_simulating(session)
    world = get_world()
    with session.write() as conn:
        meta = read_meta(conn)
        _program(conn, world, meta)
        try:
            pg.upgrade(conn, world, meta, meta.user_club_id or 0, kind, meta.current_date)
        except pg.ProgramError as exc:
            raise HTTPException(409, str(exc)) from exc
    session.autosave()
    return get_program(session)


@router.put("/settings/college-mode")
def put_college_mode(body: ModeIn, session: Session) -> ProgramOut:
    """Turn the program builder on for a college coach's career (it can't be turned off)."""
    _not_simulating(session)
    world = get_world()
    with session.write() as conn:
        meta = read_meta(conn)
        if meta.user_club_id is None or not is_college_club(conn, meta.user_club_id):
            raise HTTPException(409, "The program builder is for a college coach.")
        if body.mode != pg.BUILDER:
            raise HTTPException(409, "The program builder can't be turned off once on.")
        if meta.college_mode != pg.BUILDER:
            meta.college_mode = pg.BUILDER
            write_meta(conn, meta)
            pg.ensure_programs(conn, world, meta, meta.season_id, meta.current_date)
    session.autosave()
    return get_program(session)
