"""MLS's SuperDraft for the Draft page (W9a B5; world/draft.py): the draft's day and order, the
prospects as the user's scouts see them, the user's own ranking, the picks once made, and
signing an unsigned pick."""

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import Connection, text

from footsim.api.routes import Session, _not_simulating
from footsim.api.schemas import ClubRef
from footsim.world import draft
from footsim.world.college import draft_pool
from footsim.world.context import World, get_world
from footsim.world.meta import CareerMeta, read_meta
from footsim.world.mls import mls_club_ids
from footsim.world.squads import display_name
from footsim.world.transfers import MoveRefused

router = APIRouter(prefix="/api/draft")
BAND = 5  # the scouts' potential is shown as a band this wide


class ProspectOut(BaseModel):
    player_id: int
    name: str
    college: ClubRef
    class_year: str
    age: int
    position: str
    overall: int
    potential_low: int  # as the user's scouts see it: a band
    potential_high: int
    ga: bool  # Generation adidas
    board_rank: int | None  # where the user ranked him


class PickOut(BaseModel):
    pick: int
    round: int
    club: ClubRef
    player_id: int | None
    name: str | None
    position: str | None
    college: str | None
    signed: bool
    mine: bool


class DraftOut(BaseModel):
    season: str
    date: str  # the draft's day
    made: bool  # the draft has been made
    in_mls: bool  # the user's club is an MLS club (has picks)
    rounds: int
    picks: list[PickOut]  # every pick (to come, or made)
    prospects: list[ProspectOut]  # still in the pool, best first by the scouts' view
    board: list[int]  # the user's ranking, best first


class BoardIn(BaseModel):
    player_ids: list[int]


def _names(conn: Connection) -> dict[int, str]:
    return {int(r.id): str(r.name) for r in conn.execute(text("SELECT id, name FROM club"))}


def _draft(conn: Connection, world: World, meta: CareerMeta) -> DraftOut:
    season_id = meta.season_id
    names = _names(conn)
    user = meta.user_club_id
    when = draft.draft_date(world, conn, season_id)
    made = draft.picks(conn, world, meta, season_id)
    taken = {p.player_id for p in made if p.player_id is not None}
    people = {}
    if taken:
        people = {int(r.player_id): r for r in conn.execute(text(
            "SELECT d.player_id, d.signed, p.first_name, p.last_name, p.known_as, "
            "(SELECT position FROM player_position pp WHERE pp.player_id = p.id "
            " ORDER BY familiarity DESC LIMIT 1) AS position, c.name AS college "
            "FROM draft_pick d JOIN person p ON p.id = d.player_id "
            "LEFT JOIN college_player cp ON cp.player_id = p.id "
            "LEFT JOIN club c ON c.id = cp.club_id WHERE d.season_id = :s"),
            {"s": season_id})}
    picks = []
    for p in made:
        r = people.get(p.player_id) if p.player_id is not None else None
        picks.append(PickOut(
            pick=p.pick, round=p.round, club=ClubRef(id=p.club_id, name=names[p.club_id]),
            player_id=p.player_id,
            name=display_name(r.first_name, r.last_name, r.known_as) if r else None,
            position=r.position if r else None, college=r.college if r else None,
            signed=bool(r.signed) if r else False, mine=p.club_id == user))
    ranked = draft.board(conn, season_id, user) if user is not None else []
    rank_of = {pid: k for k, pid in enumerate(ranked, start=1)}
    sd = draft.rules(world).scouting_sd
    prospects = []
    for pr in draft_pool(conn, world, meta, season_id):
        seen = draft.scouted_potential(meta, season_id, user or 0, pr, sd)
        low = int(seen // BAND * BAND)
        prospects.append(ProspectOut(
            player_id=pr.player_id, name=pr.name,
            college=ClubRef(id=pr.college_id, name=pr.college), class_year=pr.class_year,
            age=pr.age, position=pr.position, overall=pr.overall,
            potential_low=max(low, pr.overall), potential_high=max(low + BAND, pr.overall),
            ga=pr.ga, board_rank=rank_of.get(pr.player_id)))
    prospects.sort(key=lambda x: (-(x.overall + x.potential_low), x.player_id))
    label = str(conn.execute(text("SELECT label FROM season WHERE id = :s"),
                             {"s": season_id}).scalar_one())
    return DraftOut(
        season=label, date=when.isoformat(), made=bool(taken),
        in_mls=user is not None and user in mls_club_ids(conn, world, season_id),
        rounds=draft.rules(world).rounds, picks=picks, prospects=prospects,
        board=[pid for pid in ranked if pid in {x.player_id for x in prospects}])


@router.get("")
def get_draft(session: Session) -> DraftOut:
    """This season's SuperDraft: the order, the prospects (before) or the picks (after)."""
    world = get_world()
    if world.defs.mls.league not in world.defs.leagues:
        raise HTTPException(404, "The game has no MLS.")
    with session.read() as conn:
        return _draft(conn, world, read_meta(conn))


@router.put("/board")
def put_board(body: BoardIn, session: Session) -> DraftOut:
    """The user's ranking of the prospects, best first (the draft takes the best still there)."""
    _not_simulating(session)
    world = get_world()
    with session.write() as conn:
        meta = read_meta(conn)
        if meta.user_club_id is None:
            raise HTTPException(404, "Watching only: there's no club of your own.")
        try:
            draft.set_board(conn, world, meta, meta.user_club_id, body.player_ids)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        result = _draft(conn, world, meta)
    session.autosave()
    return result


@router.post("/sign/{player_id}")
def sign(player_id: int, session: Session) -> DraftOut:
    """Sign one of the user's unsigned picks while the club holds his rights."""
    _not_simulating(session)
    world = get_world()
    with session.write() as conn:
        meta = read_meta(conn)
        day: date = meta.current_date
        try:
            draft.sign_pick(conn, world, meta, player_id, day)
        except MoveRefused as exc:
            raise HTTPException(409, str(exc)) from exc
        result = _draft(conn, world, meta)
    session.autosave()
    return result
