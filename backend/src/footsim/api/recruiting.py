"""High-school recruiting for a college coach (W9c, world/college/coach.py): the class as the
user's staff see it, their target list and scholarship offers, and the class rankings."""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from footsim.api.routes import Session, _not_simulating
from footsim.api.schemas import ClubRef
from footsim.world.college import coach
from footsim.world.context import get_world
from footsim.world.meta import read_meta

router = APIRouter(prefix="/api/recruiting")


class RecruitingOut(BaseModel):
    class_season: int
    phase: str  # before | open | late (after signing day) | closed
    start: str  # offers open
    signing_day: str
    close: str  # the class closes
    funding: float  # the program's scholarship money, in full scholarships
    returning_money: float  # held by next season's returning players
    class_money: float  # committed and signed recruits'
    offered_money: float  # open offers
    places: int  # the roster limit
    returning: int
    class_count: int  # committed and signed
    open_offers: int
    targets: int
    effort: float  # the staff's week of effort
    per_target: dict[str, float]  # a week's effort on a target of each priority
    visits_used: int
    visits: int
    prestige: int
    offer_limit: float  # open offers and the class together may be worth this much


class RangeOut(BaseModel):
    low: int
    high: int


class OfferingOut(BaseModel):
    club: ClubRef
    share: int  # percent of a full scholarship


class RecruitOut(BaseModel):
    id: int
    name: str
    stars: int
    national_rank: int
    position: str
    position_rank: int
    state: str | None  # his home state; None for a recruit from abroad
    state_rank: int | None
    nation: str  # nation code
    age: int
    overall: RangeOut  # the staff's estimate
    potential: RangeOut
    knowledge: float  # 0-1: how well the staff know him
    interest: float | None  # in the user's program, 0-100, once it recruits him
    priority: str | None  # top | high | watch: on the user's target list
    offer: float | None  # the user's offer (a share of a full scholarship; 0 a walk-on)
    offer_status: str | None  # open | pulled | accepted | declined
    offers: int  # programs offering him
    status: str  # open | committed | signed | enrolled | gone
    committed_to: ClubRef | None
    leader: ClubRef | None  # who he leans towards, when the staff know
    hopes: float  # the scholarship he hopes for
    wants: list[str]  # what matters most to him, in his words
    top: list[OfferingOut]  # his offers in order of preference, when known
    fit: str  # how he sees the user's prestige: good | reach | long_shot | out_of_reach
    expects: float  # the program prestige he hopes for
    visited_on: str | None = None  # his official visit to you, if made
    visit_fixture: int | None = None  # the home game he's invited to (game-day visit)
    portal_from: str | None = None  # a transfer portal player's D-II/D-III school


class RecruitPage(BaseModel):
    total: int
    recruits: list[RecruitOut]


class ClassRankOut(BaseModel):
    rank: int
    club: ClubRef
    recruits: int
    points: float
    stars: dict[int, int]  # recruits by stars
    mine: bool


class TargetIn(BaseModel):
    priority: Literal["top", "high", "watch"] | None


class OfferIn(BaseModel):
    share: float = Field(ge=0, le=1)  # of a full scholarship; 0 offers a walk-on place


def _ref(pair: tuple[int, str] | None) -> ClubRef | None:
    return ClubRef(id=pair[0], name=pair[1]) if pair else None


def _out(v: coach.RecruitView) -> RecruitOut:
    return RecruitOut(
        id=v.id, name=v.name, stars=v.stars, national_rank=v.national_rank, position=v.position,
        position_rank=v.position_rank, state=v.state, state_rank=v.state_rank, nation=v.nation,
        age=v.age, overall=RangeOut(low=v.overall.low, high=v.overall.high),
        potential=RangeOut(low=v.potential.low, high=v.potential.high), knowledge=v.knowledge,
        interest=v.interest, priority=v.priority, offer=v.offer, offer_status=v.offer_status,
        offers=v.offers, status=v.status, committed_to=_ref(v.committed_to),
        leader=_ref(v.leader), hopes=v.hopes, wants=v.wants,
        top=[OfferingOut(club=ClubRef(id=c, name=n), share=s) for c, n, s in v.top],
        fit=v.fit, expects=v.expects, visited_on=v.visited_on, visit_fixture=v.visit_fixture,
        portal_from=v.portal_from)


def _refused(exc: coach.RecruitingError) -> HTTPException:
    return HTTPException(409, str(exc))


@router.get("")
def get_recruiting(session: Session) -> RecruitingOut:
    with session.read() as conn:
        try:
            s = coach.summary(conn, get_world(), read_meta(conn))
        except coach.RecruitingError as exc:
            raise HTTPException(404, str(exc)) from exc
    return RecruitingOut(
        class_season=s.class_season, phase=s.phase, start=s.start.isoformat(),
        signing_day=s.signing_day.isoformat(), close=s.close.isoformat(), funding=s.funding,
        returning_money=s.returning_money, class_money=s.class_money,
        offered_money=s.offered_money, places=s.places, returning=s.returning,
        class_count=s.class_count, open_offers=s.open_offers, targets=s.targets,
        effort=s.effort, per_target=s.per_target, visits_used=s.visits_used, visits=s.visits,
        prestige=round(s.prestige), offer_limit=s.offer_limit)


VIEWS = ("board", "targets", "offers", "class", "portal")


@router.get("/recruits")
def get_recruits(session: Session, view: str = "board", position: str | None = None,
                 state: str | None = None, stars: int | None = None, q: str = "",
                 open_only: bool = False, realistic: bool = False, offset: int = 0,
                 limit: int = 50) -> RecruitPage:
    """The class by national rank, filtered: ``view`` board (everyone), targets (the user's
    list), offers (the user's open offers) or class (committed or signed to the user);
    ``realistic`` keeps the recruits who'd see the user's program as a good fit or a reach."""
    if view not in VIEWS:
        raise HTTPException(422, f"view is one of {', '.join(VIEWS)}")
    with session.read() as conn:
        meta = read_meta(conn)
        try:
            found = coach.recruits(conn, get_world(), meta)
        except coach.RecruitingError as exc:
            raise HTTPException(404, str(exc)) from exc
    user = meta.user_club_id
    groups = {"DEF": {"CB", "LB", "RB"}, "MID": {"DM", "CM", "AM"}, "ATT": {"LW", "RW", "ST"}}
    words = q.strip().lower()

    def keep(v: coach.RecruitView) -> bool:
        if view == "targets" and v.priority is None:
            return False
        if view == "offers" and v.offer_status != "open":
            return False
        if view == "class" and not (v.committed_to and v.committed_to[0] == user):
            return False
        if view == "portal" and v.portal_from is None:
            return False
        if position and v.position != position and v.position not in groups.get(position, ()):
            return False
        if state == "INTL" and v.state is not None:  # INTL: the recruits from abroad
            return False
        if state and state != "INTL" and v.state != state:
            return False
        if stars and v.stars != stars:
            return False
        if open_only and v.status != "open":
            return False
        if realistic and v.fit not in ("good", "reach"):
            return False
        return not words or words in v.name.lower()

    chosen = [v for v in found if keep(v)]
    page = chosen[max(0, offset):max(0, offset) + max(1, min(200, limit))]
    return RecruitPage(total=len(chosen), recruits=[_out(v) for v in page])


@router.get("/recruits/{recruit_id}")
def get_recruit(recruit_id: int, session: Session) -> RecruitOut:
    with session.read() as conn:
        try:
            found = coach.recruits(conn, get_world(), read_meta(conn), [recruit_id], detail=True)
        except coach.RecruitingError as exc:
            raise HTTPException(404, str(exc)) from exc
    if not found:
        raise HTTPException(404, "no such recruit in this year's class")
    return _out(found[0])


@router.put("/targets/{recruit_id}")
def put_target(recruit_id: int, body: TargetIn, session: Session) -> RecruitOut:
    _not_simulating(session)
    with session.write() as conn:
        try:
            coach.set_target(conn, get_world(), read_meta(conn), recruit_id, body.priority)
        except coach.RecruitingError as exc:
            raise _refused(exc) from exc
    session.autosave()
    return get_recruit(recruit_id, session)


@router.put("/offers/{recruit_id}")
def put_offer(recruit_id: int, body: OfferIn, session: Session) -> RecruitOut:
    _not_simulating(session)
    with session.write() as conn:
        try:
            coach.make_offer(conn, get_world(), read_meta(conn), recruit_id, body.share)
        except coach.RecruitingError as exc:
            raise _refused(exc) from exc
    session.autosave()
    return get_recruit(recruit_id, session)


@router.delete("/offers/{recruit_id}")
def delete_offer(recruit_id: int, session: Session) -> list[str]:
    _not_simulating(session)
    with session.write() as conn:
        try:
            news = coach.pull_offer(conn, get_world(), read_meta(conn), recruit_id)
        except coach.RecruitingError as exc:
            raise _refused(exc) from exc
    session.autosave()
    return news


@router.get("/classes")
def get_classes(session: Session, limit: int = 25) -> list[ClassRankOut]:
    """The class rankings so far: every program's committed and signed recruits by points; the
    top ``limit``, and the user's program wherever it is."""
    with session.read() as conn:
        meta = read_meta(conn)
        rows = coach.class_rankings(conn, get_world(), meta)
    out = []
    for rank, (club_id, name, count, points, by_stars) in enumerate(rows, start=1):
        mine = club_id == meta.user_club_id
        if rank <= limit or mine:
            out.append(ClassRankOut(rank=rank, club=ClubRef(id=club_id, name=name),
                                    recruits=count, points=points, stars=by_stars, mine=mine))
    return out


class GodPlayerOut(BaseModel):
    """The OP player (world/college/god_player.py): whether one can be signed now, and those
    signed so far."""

    available: bool
    next_season: str | None  # when the next is allowed, if not now
    every_seasons: int
    overall: int  # about what he's rated
    signed: list[ClubRef]  # the players (id, name), latest first


def _god_status(session: Session) -> GodPlayerOut:
    from footsim.persistence.schema import person
    from footsim.world.college import god_player
    from footsim.world.squads import display_name

    with session.read() as conn:
        meta = read_meta(conn)
        found = god_player.status(conn, get_world(), meta)
        names = {int(r.id): display_name(r.first_name, r.last_name, r.known_as)
                 for r in conn.execute(person.select().where(
                     person.c.id.in_([pid for pid, _ in found.signed])))}
    return GodPlayerOut(available=found.available, next_season=found.next_season,
                        every_seasons=found.every_seasons, overall=found.overall,
                        signed=[ClubRef(id=pid, name=names.get(pid, "?"))
                                for pid, _ in found.signed])


@router.get("/god-player")
def get_god_player(session: Session) -> GodPlayerOut:
    return _god_status(session)


@router.post("/god-player")
def post_god_player(session: Session) -> GodPlayerOut:
    """Sign this season's OP player: a freshman with a pro's ratings, at a random position."""
    from footsim.world.college import god_player

    _not_simulating(session)
    with session.write() as conn:
        meta = read_meta(conn)
        try:
            god_player.sign(conn, get_world(), meta, meta.current_date)
        except god_player.GodPlayerRefused as exc:
            raise HTTPException(409, str(exc)) from exc
    session.autosave()
    return _god_status(session)



class HomeGameOut(BaseModel):
    fixture_id: int
    date: str
    opponent: str
    invited: list[int]  # recruit ids


class HomeGamesOut(BaseModel):
    games: list[HomeGameOut]  # your home games before signing day
    per_game: int
    visits_used: int  # official visits made or arranged this class
    visits: int  # the season's allowance


class VisitIn(BaseModel):
    fixture_id: int | None  # None: call it off


@router.get("/home-games")
def get_home_games(session: Session) -> HomeGamesOut:
    """The home games a recruit can visit (world/college/visits.py)."""
    from footsim.world.college import visits

    world = get_world()
    with session.read() as conn:
        meta = read_meta(conn)
        games = visits.home_games(conn, world, meta)
        used = visits.visits_used(conn, meta, meta.user_club_id or 0)
    rules = world.defs.college.recruiting.programs
    return HomeGamesOut(
        games=[HomeGameOut(fixture_id=g.fixture_id, date=g.date.isoformat(),
                           opponent=g.opponent, invited=g.invited) for g in games],
        per_game=rules.gameday_visit.per_game, visits_used=used, visits=rules.official_visits)


@router.put("/visits/{recruit_id}")
def put_visit(recruit_id: int, body: VisitIn, session: Session) -> RecruitOut:
    """Invite a recruit to a home game for his official visit, or call it off."""
    from footsim.world.college import visits

    _not_simulating(session)
    with session.write() as conn:
        try:
            visits.invite(conn, get_world(), read_meta(conn), recruit_id, body.fixture_id)
        except (visits.VisitRefused, coach.RecruitingError) as exc:
            raise HTTPException(409, str(exc)) from exc
    session.autosave()
    return get_recruit(recruit_id, session)



class AssistantOut(BaseModel):
    auto: bool  # the assistant recruits your leavers' replacements
    leaving: dict[str, int]  # your leavers after this season, by position group


class AssistantIn(BaseModel):
    auto: bool


def _assistant(session: Session) -> AssistantOut:
    from footsim.world.college.assistant import leaving

    with session.read() as conn:
        meta = read_meta(conn)
        return AssistantOut(auto=meta.auto_recruiting,
                            leaving=dict(leaving(conn, get_world(), meta)))


@router.get("/assistant")
def get_assistant(session: Session) -> AssistantOut:
    return _assistant(session)


@router.put("/assistant")
def put_assistant(body: AssistantIn, session: Session) -> AssistantOut:
    """The recruiting assistant on or off: switched on, it recruits at once (from the day offers
    open until signing day), then every Monday."""
    from footsim.world.college.assistant import recruit_for_leavers
    from footsim.world.meta import write_meta

    _not_simulating(session)
    with session.write() as conn:
        meta = read_meta(conn)
        meta.auto_recruiting = body.auto
        write_meta(conn, meta)
        if body.auto:
            recruit_for_leavers(conn, get_world(), meta, meta.current_date)
    session.autosave()
    return _assistant(session)
