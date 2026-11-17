"""Settings → Simulation (world/fast_sim.py): which leagues are fully simulated and which get
fast results. The choices are the game's leagues and the NCAA's college season; the user's own
league is always fully simulated."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from footsim.api.routes import Session, _not_simulating
from footsim.world import fast_sim
from footsim.world.context import World, get_world
from footsim.world.meta import read_meta, write_meta

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
