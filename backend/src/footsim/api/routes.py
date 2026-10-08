"""REST endpoints. Thin: validation and orchestration only; logic lives in world/ and match/."""

from datetime import date
from functools import cache
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select

from footsim import __version__
from footsim.api import calendar as calendar_view
from footsim.api import finances, queries, season_review, sim
from footsim.api.schemas import (
    AdvanceOut,
    BoardIn,
    CareerOut,
    ClubHistoryOut,
    ClubOverviewOut,
    ClubPlayerOut,
    CompetitionOut,
    CupOut,
    CupSummaryOut,
    FinancesOut,
    FixtureOut,
    LeagueOption,
    MatchOut,
    NewCareerIn,
    PlayerDetailOut,
    PlayerSeasonOut,
    SaveSlotOut,
    SeasonOut,
    SquadPlayerOut,
    TableOut,
    TacticsIn,
    TacticsOut,
)
from footsim.api.session import CareerSession, NoCareer
from footsim.core.build_info import build_info
from footsim.core.paths import DEFAULT_SAVES
from footsim.persistence.schema import fixture
from footsim.world.career import advance, play_user_instant, set_user_tactic
from footsim.world.context import get_world
from footsim.world.finance import set_board_enabled
from footsim.world.meta import read_meta

router = APIRouter(prefix="/api")


def get_session(request: Request) -> CareerSession:
    session: CareerSession = request.app.state.session
    return session


Session = Annotated[CareerSession, Depends(get_session)]


@router.get("/health")
def health(session: Session) -> dict[str, str | bool]:
    """Liveness, where this server keeps its saves, and which build it is. The browser tests
    refuse to run unless it says the saves aren't in the default folder, where the user's own
    careers live: each test starts a career, which overwrites save slot 1. The build (version
    number such as "1.12", commit, its date, branch, and whether tracked files have changed
    since) is what the version tag in the game shows; ``package_version`` is the Python package's
    own. ``in_use`` says whether a match is being played live or a sim-to-date is running: the
    updater waits for neither (an open page doesn't count; it reconnects after a restart)."""
    saves = session.saves.root.resolve()
    in_use = bool(session.live_matches) or sim.running(session)
    return {"status": "ok", "package_version": __version__, "saves_dir": str(saves),
            "default_saves": saves == DEFAULT_SAVES.resolve(), "in_use": in_use, **build_info()}


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
    if session.slot is None:
        raise NoCareer("no career loaded")
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
    session.new_career(slot, body.club_id, body.manager_name.strip() or "Manager",
                       body.budget_eur, body.board_enabled)
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


def _not_simulating(session: CareerSession) -> None:
    if sim.running(session):
        raise HTTPException(409, "the game is simulating to a date: stop it or let it finish")


@router.post("/career/advance")
def advance_career(session: Session) -> AdvanceOut:
    _not_simulating(session)
    world = get_world()
    with session.write() as conn:
        result = advance(conn, world)
    session.autosave()
    final = None
    if result.stop == "season_end":
        with session.read() as conn:
            user = read_meta(conn).user_club_id
            if user is not None:
                final = season_review.season_final(conn, world, user, result.messages)
    return AdvanceOut(date=result.date.isoformat(), stop=result.stop,
                      fixture_id=result.fixture_id, messages=result.messages,
                      season_final=final)


@router.get("/finances")
def club_finances(session: Session) -> FinancesOut:
    """The user's club's money: balance, budget, wages against what the income supports, a
    month's money at today's rates and its recent changes, the one-off transactions and (when
    the board is on) the board's view."""
    with session.read() as conn:
        try:
            return finances.finances(conn, get_world())
        except finances.NoClub as exc:
            raise HTTPException(404, "watching only: no club of your own") from exc


@router.put("/career/board")
def put_board(body: BoardIn, session: Session) -> FinancesOut:
    """Turn the user's board on or off. The budget is worked out again at once: all the club's
    cash without a board, the board's plan with one."""
    _not_simulating(session)
    world = get_world()
    with session.write() as conn:
        meta = read_meta(conn)
        if meta.user_club_id is None:
            raise HTTPException(404, "watching only: no club of your own")
        set_board_enabled(conn, world, meta, body.enabled)
    session.autosave()
    with session.read() as conn:
        return finances.finances(conn, world)


@router.get("/competitions")
def competitions(session: Session) -> list[CompetitionOut]:
    with session.read() as conn:
        return queries.competitions(conn, get_world())


@router.get("/competitions/{key}/table")
def competition_table(key: str, session: Session, season: int | None = None) -> TableOut:
    with session.read() as conn:
        return queries.table(conn, get_world(), key, season)


@router.get("/seasons")
def seasons(session: Session) -> list[SeasonOut]:
    """Every season of the career so far, newest first."""
    with session.read() as conn:
        return queries.seasons(conn)


@router.get("/cups")
def cups(session: Session) -> list[CupSummaryOut]:
    """This season's cups."""
    with session.read() as conn:
        return queries.cups(conn, get_world())


@router.get("/cups/{key}")
def cup(key: str, session: Session, season: int | None = None) -> CupOut:
    """A cup's rounds and ties, this season or ``season``."""
    if key not in get_world().defs.cups:
        raise HTTPException(404, "no such cup")
    with session.read() as conn:
        return queries.cup(conn, get_world(), key, season)


@router.get("/competitions/{key}/fixtures")
def competition_fixtures(key: str, session: Session) -> list[FixtureOut]:
    with session.read() as conn:
        return queries.fixtures(conn, competition_key=key)


@router.get("/clubs/{club_id}")
def club_profile(club_id: int, session: Session) -> ClubOverviewOut:
    with session.read() as conn:
        try:
            return queries.club_overview(conn, get_world(), club_id)
        except queries.ClubNotFound as exc:
            raise HTTPException(404, "club not found") from exc


@router.get("/clubs/{club_id}/players")
def club_players(club_id: int, session: Session) -> list[ClubPlayerOut]:
    """Any club's squad, as seen from outside it."""
    with session.read() as conn:
        try:
            return queries.club_players(conn, get_world(), club_id)
        except queries.ClubNotFound as exc:
            raise HTTPException(404, "club not found") from exc


@router.get("/clubs/{club_id}/squad")
def club_squad(club_id: int, session: Session) -> list[SquadPlayerOut]:
    """The user's own squad in full (fitness, wages): other clubs are browsed via /players."""
    with session.read() as conn:
        if club_id != read_meta(conn).user_club_id:
            raise HTTPException(403, "only your own club's squad details are available")
        return queries.squad(conn, get_world(), club_id)


@router.get("/clubs/{club_id}/history")
def club_history(club_id: int, session: Session) -> ClubHistoryOut:
    """A club's league seasons in this career, newest first."""
    with session.read() as conn:
        try:
            return queries.club_history(conn, get_world(), club_id)
        except queries.ClubNotFound as exc:
            raise HTTPException(404, "club not found") from exc


@router.get("/calendar")
def calendar_range(session: Session, start: Annotated[date, Query(alias="from")],
                   to: date) -> calendar_view.CalendarOut:
    """The user's fixtures, window days and breaks from ``from`` to ``to``."""
    if to < start or (to - start).days > calendar_view.MAX_RANGE_DAYS:
        raise HTTPException(422, "a range of at most 400 days, ending after it starts")
    if session.slot is None:
        raise NoCareer("no career loaded")
    with session.read() as conn:
        return calendar_view.calendar(conn, get_world(), start, to)


@router.get("/clubs/{club_id}/fixtures")
def club_fixtures(club_id: int, session: Session, season: int | None = None) -> list[FixtureOut]:
    """A club's fixtures and results in every competition, this season or ``season``."""
    with session.read() as conn:
        return queries.fixtures(conn, club_id=club_id, season_id=season)


@router.get("/players/{player_id}")
def player(player_id: int, session: Session) -> PlayerDetailOut:
    with session.read() as conn:
        try:
            return queries.player_detail(conn, get_world(), player_id)
        except KeyError as exc:
            raise HTTPException(404, "player not found") from exc


@router.get("/players/{player_id}/seasons")
def player_seasons(player_id: int, session: Session) -> list[PlayerSeasonOut]:
    """A player's record in each season and competition, the current season first."""
    with session.read() as conn:
        try:
            return queries.player_seasons(conn, get_world(), player_id)
        except KeyError as exc:
            raise HTTPException(404, "player not found") from exc


@router.post("/players/{player_id}/release")
def release_player(player_id: int, session: Session) -> PlayerDetailOut:
    """Release one of the user's players: his contract ends and he becomes a free agent."""
    _not_simulating(session)
    if session.live_matches:
        raise HTTPException(409, "finish the match being played first")
    with session.write() as conn:
        try:
            queries.release_player(conn, get_world(), player_id, read_meta(conn).current_date)
        except KeyError as exc:
            raise HTTPException(400, "not one of your players") from exc
        except queries.SquadTooSmall as exc:
            raise HTTPException(409, f"{exc} There are no transfers yet to replace him.") from exc
    session.autosave()
    with session.read() as conn:
        return queries.player_detail(conn, get_world(), player_id)


@router.get("/fixtures/{fixture_id}")
def match(fixture_id: int, session: Session) -> MatchOut:
    with session.read() as conn:
        return queries.match_detail(conn, fixture_id)


@router.post("/fixtures/{fixture_id}/play")
def play_now(fixture_id: int, session: Session) -> MatchOut:
    """Instant result for the user's match of the day."""
    _not_simulating(session)
    world = get_world()
    if fixture_id in session.live_matches:
        raise HTTPException(409, "this match is being played live: finish it in the match view")
    with session.write() as conn:
        meta = read_meta(conn)
        fx = conn.execute(select(fixture).where(fixture.c.id == fixture_id)).first()
        if fx is None or fx.status != "scheduled":
            raise HTTPException(400, "fixture is not waiting to be played")
        if meta.user_club_id not in (fx.home_club_id, fx.away_club_id):
            raise HTTPException(400, "not your match")
        if fx.date != meta.current_date.isoformat():
            raise HTTPException(400, "this match isn't today")
        play_user_instant(conn, world, meta, fx, meta.current_date)
    session.autosave()
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
