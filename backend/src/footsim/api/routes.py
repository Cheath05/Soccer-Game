"""REST endpoints. Thin: validation and orchestration only; logic lives in world/ and match/."""

from functools import cache
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from footsim import __version__
from footsim.api import queries
from footsim.api.schemas import (
    AdvanceOut,
    CareerOut,
    CompetitionOut,
    FixtureOut,
    LeagueOption,
    MatchOut,
    NewCareerIn,
    PlayerDetailOut,
    SaveSlotOut,
    SquadPlayerOut,
    TableOut,
    TacticsIn,
    TacticsOut,
)
from footsim.api.session import CareerSession
from footsim.persistence.schema import fixture
from footsim.world.career import advance, play_fixture, set_user_tactic
from footsim.world.context import get_world
from footsim.world.meta import read_meta

router = APIRouter(prefix="/api")


def get_session(request: Request) -> CareerSession:
    session: CareerSession = request.app.state.session
    return session


Session = Annotated[CareerSession, Depends(get_session)]


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@cache
def _leagues(base_world: Path) -> list[LeagueOption]:
    return queries.world_leagues(base_world, get_world())


@router.get("/world/leagues")
def world_leagues(session: Session) -> list[LeagueOption]:
    if not session.base_world.exists():
        raise HTTPException(503, "No base world built yet: run `just build-world`.")
    return _leagues(session.base_world)


@router.get("/saves")
def saves(session: Session) -> list[SaveSlotOut]:
    result = []
    for s in session.saves.list_slots():
        meta = s.meta
        result.append(SaveSlotOut(
            slot=s.slot, has_save=s.has_save, has_autosave=s.has_autosave, saved_at=s.saved_at,
            club=meta.get("club_name"), manager=meta.get("manager_name"),
            game_date=meta.get("game_date"), active=session.slot == s.slot,
        ))
    return result


def _career(session: CareerSession) -> CareerOut:
    assert session.slot is not None
    with session.read() as conn:
        return queries.career(conn, get_world(), session.slot)


def _record_club_name(session: CareerSession) -> None:
    """Keep the club name in game_meta so the load screen can show it."""
    from footsim.persistence.database import write_meta

    career = _career(session)
    write_meta(session.engine, {"club_name": career.club.name})


@router.post("/saves/{slot}/new")
def new_career(slot: int, body: NewCareerIn, session: Session) -> CareerOut:
    if not session.base_world.exists():
        raise HTTPException(503, "No base world built yet: run `just build-world`.")
    session.new_career(slot, body.club_id, body.manager_name.strip() or "Manager")
    _record_club_name(session)
    session.save()
    return _career(session)


@router.post("/saves/{slot}/load")
def load_career(slot: int, session: Session, autosave: bool = False) -> CareerOut:
    session.load(slot, autosave=autosave)
    return _career(session)


@router.post("/saves/save")
def save_career(session: Session) -> list[SaveSlotOut]:
    session.save()
    return saves(session)


@router.get("/career")
def get_career(session: Session) -> CareerOut:
    return _career(session)


@router.post("/career/advance")
def advance_career(session: Session) -> AdvanceOut:
    with session.write() as conn:
        result = advance(conn, get_world())
    session.autosave()
    return AdvanceOut(date=result.date.isoformat(), stop=result.stop,
                      fixture_id=result.fixture_id, messages=result.messages)


@router.get("/competitions")
def competitions(session: Session) -> list[CompetitionOut]:
    with session.read() as conn:
        return queries.competitions(conn, get_world())


@router.get("/competitions/{key}/table")
def competition_table(key: str, session: Session, season: int | None = None) -> TableOut:
    with session.read() as conn:
        return queries.table(conn, get_world(), key, season)


@router.get("/competitions/{key}/fixtures")
def competition_fixtures(key: str, session: Session) -> list[FixtureOut]:
    with session.read() as conn:
        return queries.fixtures(conn, competition_key=key)


@router.get("/clubs/{club_id}/squad")
def club_squad(club_id: int, session: Session) -> list[SquadPlayerOut]:
    with session.read() as conn:
        return queries.squad(conn, get_world(), club_id)


@router.get("/clubs/{club_id}/fixtures")
def club_fixtures(club_id: int, session: Session) -> list[FixtureOut]:
    with session.read() as conn:
        return queries.fixtures(conn, club_id=club_id)


@router.get("/players/{player_id}")
def player(player_id: int, session: Session) -> PlayerDetailOut:
    with session.read() as conn:
        try:
            return queries.player_detail(conn, get_world(), player_id)
        except KeyError as exc:
            raise HTTPException(404, "player not found") from exc


@router.get("/fixtures/{fixture_id}")
def match(fixture_id: int, session: Session) -> MatchOut:
    with session.read() as conn:
        return queries.match_detail(conn, fixture_id)


@router.post("/fixtures/{fixture_id}/play")
def play_now(fixture_id: int, session: Session) -> MatchOut:
    """Instant result for the user's match of the day."""
    world = get_world()
    with session.write() as conn:
        meta = read_meta(conn)
        fx = conn.execute(select(fixture).where(fixture.c.id == fixture_id)).first()
        if fx is None or fx.status != "scheduled":
            raise HTTPException(400, "fixture is not waiting to be played")
        if meta.user_club_id not in (fx.home_club_id, fx.away_club_id):
            raise HTTPException(400, "not your match")
        if fx.date != meta.current_date.isoformat():
            raise HTTPException(400, "this match isn't today")
        play_fixture(conn, world, meta, fx, meta.current_date, sim="instant")
    with session.read() as conn:
        return queries.match_detail(conn, fixture_id)


@router.get("/tactics")
def get_tactics(session: Session) -> TacticsOut:
    with session.read() as conn:
        return queries.tactics(conn, get_world())


@router.put("/tactics")
def put_tactics(body: TacticsIn, session: Session) -> TacticsOut:
    world = get_world()
    try:
        with session.write() as conn:
            set_user_tactic(conn, world, body.formation, body.roles, body.lineup,
                            body.instructions)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    with session.read() as conn:
        return queries.tactics(conn, world)
