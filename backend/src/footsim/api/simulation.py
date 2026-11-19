"""The career's settings. Simulation (world/fast_sim.py): which leagues are fully simulated and
which get fast results; the choices are the game's leagues and the NCAA's college season, and the
user's own league is always fully simulated. Transfer offers (world/offers.py): whether bids for
the user's players stop the game, wait, or are answered by the user's asking prices."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from footsim.api.routes import Session, _not_simulating
from footsim.world import fast_sim, offers
from footsim.world.context import World, get_world
from footsim.world.meta import CareerMeta, read_meta, write_meta
from footsim.world.transfers import owner_contract

router = APIRouter(prefix="/api")


class SimLeagueOut(BaseModel):
    key: str
    name: str
    nation: str  # a nation code such as ENG
    tier: int


class SimulationOut(BaseModel):
    fast: list[str]  # the leagues given fast results
    user_league: str | None  # always fully simulated, whatever ``fast`` says


class SimulationIn(BaseModel):
    fast: list[str]


def _choices(world: World) -> list[SimLeagueOut]:
    leagues = [SimLeagueOut(key=k, name=lg.name, nation=lg.nation, tier=lg.tier)
               for k, lg in world.defs.leagues.items()]
    college = world.defs.college.rules
    leagues.append(SimLeagueOut(key=college.key, name=college.name, nation="USA",
                                tier=max(lg.tier for lg in leagues if lg.nation == "USA") + 1))
    return sorted(leagues, key=lambda lg: (lg.nation, lg.tier, lg.key))


@router.get("/world/simulation")
def simulation_choices() -> list[SimLeagueOut]:
    """Every league that can be switched to fast results (no career needed: the start page)."""
    return _choices(get_world())


@router.get("/settings/simulation")
def get_simulation(session: Session) -> SimulationOut:
    with session.read() as conn:
        meta = read_meta(conn)
        return SimulationOut(fast=meta.fast_leagues, user_league=fast_sim.user_league(conn, meta))


@router.put("/settings/simulation")
def put_simulation(body: SimulationIn, session: Session) -> SimulationOut:
    """Choose the leagues given fast results, from the next day played."""
    _not_simulating(session)
    world = get_world()
    with session.write() as conn:
        meta = read_meta(conn)
        try:
            fast_sim.set_fast_leagues(world, meta, body.fast)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        write_meta(conn, meta)
        result = SimulationOut(fast=meta.fast_leagues,
                               user_league=fast_sim.user_league(conn, meta))
    session.autosave()
    return result


# --- Settings → Transfer offers (world/offers.py) ----------------------------------------


class OfferRulesOut(BaseModel):
    mode: str  # stop | wait | auto
    value_pct: int | None  # "auto": sell a player without an asking price at this % of value
    loans: str  # "auto": accept | reject loan requests
    asking_prices: dict[int, int]  # by player id, in EUR


class OfferRulesIn(BaseModel):
    mode: str
    value_pct: int | None = None
    loans: str = "reject"


def _rules_out(meta: CareerMeta) -> OfferRulesOut:
    return OfferRulesOut(mode=meta.offer_mode, value_pct=meta.offer_value_pct,
                         loans=meta.offer_loans, asking_prices=meta.asking_prices)


@router.get("/settings/offers")
def get_offer_rules(session: Session) -> OfferRulesOut:
    with session.read() as conn:
        return _rules_out(read_meta(conn))


@router.put("/settings/offers")
def put_offer_rules(body: OfferRulesIn, session: Session) -> OfferRulesOut:
    """How bids for the user's players are handled while the game moves on."""
    _not_simulating(session)
    with session.write() as conn:
        meta = read_meta(conn)
        try:
            offers.set_offer_rules(meta, body.mode, body.value_pct, body.loans)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        write_meta(conn, meta)
        result = _rules_out(meta)
    session.autosave()
    return result


class AskingPriceIn(BaseModel):
    fee_eur: int | None  # None: no asking price


@router.put("/settings/asking-price/{player_id}")
def put_asking_price(player_id: int, body: AskingPriceIn, session: Session) -> OfferRulesOut:
    """The price the user wants for one of their players (used when offers are answered
    automatically)."""
    _not_simulating(session)
    with session.write() as conn:
        meta = read_meta(conn)
        owner = owner_contract(conn, player_id)
        if owner is None or owner.club_id != meta.user_club_id:
            raise HTTPException(400, "not one of your players")
        try:
            offers.set_asking_price(meta, player_id, body.fee_eur)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        write_meta(conn, meta)
        result = _rules_out(meta)
    session.autosave()
    return result
