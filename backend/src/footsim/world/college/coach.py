"""A college coach's recruiting (W9c): what the user sees of the class, and what they can do.

The user puts recruits on their target list with a priority (top, high or watch); the staff
spread the program's weekly effort over the list (world/college/recruiting.py ``_effort``), which
builds each recruit's interest and the staff's knowledge of him. The user offers scholarships
(a share of a full one, or a walk-on place) within the program's money and places, change them or
pull them. What they see of a recruit's ability is an estimate that narrows with knowledge; who a
recruit leans towards is known once the staff know him, or for the best-known recruits."""

import math
from collections import Counter
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Connection, select

from footsim.core.rng import derive_rng
from footsim.persistence.schema import club, nation, recruit
from footsim.world.college import recruiting as rc
from footsim.world.context import World
from footsim.world.meta import CareerMeta

PHASE_BEFORE = "before"  # the class is ranked; offers open on the calendar's start
PHASE_OPEN = "open"  # offers, commitments
PHASE_LATE = "late"  # after signing day: open recruits sign when they decide
PHASE_CLOSED = "closed"  # the class has closed; it enrolls at the rollover


class RecruitingError(ValueError):
    """An action the rules refuse, with the reason for the user."""


@dataclass(frozen=True)
class Estimate:
    low: int
    high: int


def estimate(seed: int, recruit_id: int, kind: str, truth: float, knowledge: float,
             error_sd: float, width: float, floor: float) -> Estimate:
    """The staff's range for a recruit's ``kind`` (overall or potential): the truth plus a fixed
    error that shrinks with knowledge, as wide as ``width`` at no knowledge."""
    bias = float(derive_rng(seed, "recruit-estimate", kind, recruit_id).normal(0.0, error_sd))
    centre = truth + bias * (1.0 - knowledge)
    half = max(floor, width * (1.0 - knowledge)) / 2 + 0.5
    return Estimate(max(1, math.floor(centre - half)), min(99, math.ceil(centre + half)))


def phase(world: World, conn: Connection, meta: CareerMeta) -> tuple[str, rc.RecruitingDates]:
    dates = rc.recruiting_dates(world.defs.college.recruiting,
                                rc.season_start(conn, meta.season_id))
    day = meta.current_date
    if day < dates.start:
        return PHASE_BEFORE, dates
    if day < dates.signing_day:
        return PHASE_OPEN, dates
    if day < dates.close:
        return PHASE_LATE, dates
    return PHASE_CLOSED, dates


def _board(conn: Connection, world: World, meta: CareerMeta) -> tuple[rc.Board, int]:
    board = rc.load_board(conn, world, meta, meta.season_id + 1, meta.current_date)
    user = board.user_program()
    if user is None:
        raise RecruitingError("Recruiting is for a college coach.")
    return board, user


# --- what the user sees ------------------------------------------------------------------------


@dataclass
class Summary:
    class_season: int
    phase: str
    start: date
    signing_day: date
    close: date
    funding: float
    returning_money: float
    class_money: float  # committed and signed
    offered_money: float  # open offers
    places: int  # the roster limit
    returning: int
    class_count: int
    open_offers: int
    targets: int
    effort: float  # the staff's week
    per_target: dict[str, float]  # effort a week on a target of each priority
    visits_used: int
    visits: int
    prestige: float
    offer_limit: float  # open offers and the class together may be worth this much


def summary(conn: Connection, world: World, meta: CareerMeta) -> Summary:
    board, user = _board(conn, world, meta)
    hs = board.hs
    p = board.programs[user]
    stage, dates = phase(world, conn, meta)
    offers = [o for o in board.by_club.get(user, {}).values() if o.status == rc.OFFERED]
    targets = [row for row in board.rows_by_club.get(user, {}).values()
               if row.priority is not None
               and board.recruits[row.recruit_id].status in (rc.OPEN, rc.COMMITTED)]
    total = sum(hs.programs.priority_weight[row.priority or rc.WATCH] for row in targets)
    per = {k: round(min(hs.programs.effort_cap, p.effort * w / total), 1) if total else
           round(min(hs.programs.effort_cap, p.effort), 1)
           for k, w in hs.programs.priority_weight.items()}
    return Summary(
        class_season=board.class_season, phase=stage, start=dates.start,
        signing_day=dates.signing_day, close=dates.close, funding=p.funding,
        returning_money=round(p.returning_money, 2), class_money=round(p.class_money, 2),
        offered_money=round(sum(o.share for o in offers), 2),
        places=hs.programs.roster_max, returning=p.returning_count, class_count=p.class_count,
        open_offers=len(offers), targets=len(targets), effort=p.effort, per_target=per,
        visits_used=p.visits, visits=hs.programs.official_visits, prestige=p.prestige,
        offer_limit=round(max(0.0, p.money_left()) * hs.programs.offer_overcommit
                          + p.class_money, 2))


@dataclass
class RecruitView:
    id: int
    name: str
    stars: int
    national_rank: int
    position: str
    position_rank: int
    state: str | None
    state_rank: int | None
    nation: str
    age: int
    overall: Estimate
    potential: Estimate
    knowledge: float
    interest: float | None  # in the user's program, once it recruits him
    priority: str | None
    offer: float | None  # the user's open (or accepted) offer
    offer_status: str | None
    offers: int  # programs offering him
    status: str
    committed_to: tuple[int, str] | None
    leader: tuple[int, str] | None  # who he leans towards, when known
    hopes: float  # the scholarship he hopes for
    wants: list[str]  # what he cares about most, in his words
    top: list[tuple[int, str, int]]  # his offers by his preference (club, name, share %), if known


WANTS = {
    "money": "A big scholarship",
    "prestige": "A big-name program",
    "playing_time": "To play right away",
    "home": "To stay close to home",
    "attention": "Coaches who show they care",
}


def _view(board: rc.Board, user: int, r: rc.Recruit, names: dict[int, str],
          nations: dict[int, str], starters: Counter[str], detail: bool) -> RecruitView:
    hs = board.hs
    ux = hs.user
    row = board.interest.get((r.id, user))
    knowledge = row.knowledge if row else 0.0
    offer = board.offers.get((r.id, user))
    offers = board.offers_to(r.id)
    known = knowledge >= ux.leader_knowledge or r.national_rank <= ux.leader_rank
    ranked: list[tuple[float, rc.Offer]] = []
    if (known or detail) and offers:
        ranked = rc._choices(board, r, starters)
    leader = None
    if r.club_id is not None:
        leader = (r.club_id, names[r.club_id])
    elif known and ranked:
        leader = (ranked[0][1].club_id, names[ranked[0][1].club_id])
    truth_potential = r.potential
    overall = estimate(board.meta.seed, r.id, "overall", r.overall, knowledge,
                       ux.overall_error_sd, ux.overall_width, ux.width_floor)
    potential = estimate(board.meta.seed, r.id, "potential", truth_potential, knowledge,
                         ux.potential_error_sd, ux.potential_width, ux.width_floor)
    potential = rc_max(potential, overall)
    wants = [WANTS[k] for k, _ in sorted(((k, r.priorities.get(k, 1.0)) for k in WANTS),
                                         key=lambda kv: -kv[1])[:2]]
    born = date.fromisoformat(r.birth_date)
    today = board.day
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return RecruitView(
        id=r.id, name=r.name, stars=r.stars, national_rank=r.national_rank,
        position=r.position, position_rank=r.position_rank, state=r.state,
        state_rank=r.state_rank, nation=nations[r.nation_id], age=age,
        overall=overall, potential=potential, knowledge=round(knowledge, 2),
        interest=round(row.interest, 1) if row else None,
        priority=row.priority if row else None,
        offer=offer.share if offer and offer.status in (rc.OFFERED, rc.ACCEPTED) else None,
        offer_status=offer.status if offer else None, offers=len(offers), status=r.status,
        committed_to=(r.club_id, names[r.club_id]) if r.club_id is not None else None,
        leader=leader, hopes=round(r.expected_share, 2), wants=wants,
        top=[(o.club_id, names[o.club_id], round(o.share * 100)) for _s, o in ranked[:5]]
        if (known or detail) else [])


def rc_max(potential: Estimate, overall: Estimate) -> Estimate:
    """A potential range never below the overall's."""
    return Estimate(max(potential.low, overall.low), max(potential.high, overall.high))


def recruits(conn: Connection, world: World, meta: CareerMeta,
             ids: list[int] | None = None, detail: bool = False) -> list[RecruitView]:
    """The class as the user sees it (or the recruits ``ids``), by national rank."""
    board, user = _board(conn, world, meta)
    names = {int(r.id): str(r.name) for r in conn.execute(select(club.c.id, club.c.name))}
    nations = {int(r.id): str(r.code) for r in conn.execute(select(nation.c.id, nation.c.code))}
    starters = rc.starters(world)
    chosen = [board.recruits[i] for i in ids if i in board.recruits] if ids is not None \
        else list(board.recruits.values())
    views = [_view(board, user, r, names, nations, starters, detail) for r in chosen]
    return sorted(views, key=lambda v: v.national_rank)


def class_rankings(conn: Connection, world: World, meta: CareerMeta
                   ) -> list[tuple[int, str, int, float, dict[int, int]]]:
    """Every program's class so far (committed and signed): (club, name, recruits, points,
    recruits by stars), best first."""
    points = world.defs.college.recruiting.user.class_points
    found: dict[int, list[int]] = {}
    for r in conn.execute(select(recruit.c.club_id, recruit.c.stars).where(
            recruit.c.class_season == meta.season_id + 1,
            recruit.c.status.in_((rc.COMMITTED, rc.SIGNED, rc.JOINED)))):
        found.setdefault(int(r.club_id), []).append(int(r.stars))
    names = {int(r.id): str(r.name) for r in conn.execute(select(club.c.id, club.c.name))}
    rows = []
    for club_id, stars in found.items():
        by_stars: dict[int, int] = {s: stars.count(s) for s in (5, 4, 3, 2) if s in stars}
        rows.append((club_id, names[club_id], len(stars),
                     float(sum(points.get(s, 0.0) for s in stars)), by_stars))
    return sorted(rows, key=lambda x: (-x[3], -x[2], x[1]))


# --- what the user does ------------------------------------------------------------------------


def set_target(conn: Connection, world: World, meta: CareerMeta, recruit_id: int,
               priority: str | None) -> None:
    """Put a recruit on the target list with ``priority`` (top, high or watch), or take him off
    (None)."""
    board, user = _board(conn, world, meta)
    r = board.recruits.get(recruit_id)
    if r is None:
        raise RecruitingError("No such recruit in this year's class.")
    if priority is not None and priority not in (rc.TOP, rc.HIGH, rc.WATCH):
        raise RecruitingError(f"Unknown priority: {priority}.")
    if priority is not None and r.status not in (rc.OPEN, rc.COMMITTED):
        raise RecruitingError(f"{r.name} has signed: he's no longer recruiting.")
    row = board.interest_row(recruit_id, user)
    row.priority, row.changed = priority, True
    rc.save_board(conn, board)


def make_offer(conn: Connection, world: World, meta: CareerMeta, recruit_id: int,
               share: float) -> None:
    """Offer a recruit a scholarship (a share of a full one, in steps; 0 is a walk-on place),
    or change the offer. It goes on the target list (as watch) if it isn't there."""
    board, user = _board(conn, world, meta)
    hs = board.hs
    stage, dates = phase(world, conn, meta)
    if stage == PHASE_BEFORE:
        raise RecruitingError(f"Offers open on {dates.start:%-d %B}.")
    if stage == PHASE_CLOSED:
        raise RecruitingError("This year's class has closed: offers open again next season.")
    r = board.recruits.get(recruit_id)
    if r is None:
        raise RecruitingError("No such recruit in this year's class.")
    if r.status not in (rc.OPEN, rc.COMMITTED) or (r.status == rc.COMMITTED
                                                   and r.club_id == user):
        done = "committed to you" if r.club_id == user else "signed"
        raise RecruitingError(f"{r.name} has already {done}.")
    step = hs.programs.share_step
    share = round(round(share / step) * step, 2)
    if not 0.0 <= share <= 1.0:
        raise RecruitingError("An offer is between a walk-on place and a full scholarship.")
    p = board.programs[user]
    current = board.offers.get((recruit_id, user))
    others = sum(o.share for o in board.by_club.get(user, {}).values()
                 if o.status == rc.OFFERED and o.recruit_id != recruit_id)
    count = sum(1 for o in board.by_club.get(user, {}).values()
                if o.status == rc.OFFERED and o.recruit_id != recruit_id)
    money_limit = max(0.0, p.money_left()) * hs.programs.offer_overcommit
    if others + share > money_limit + 1e-6:
        raise RecruitingError(
            f"Your offers out would be worth {others + share:.2f} scholarships: with "
            f"{max(0.0, p.money_left()):.2f} left you can have at most {money_limit:.2f} on offer.")
    places = p.places_left(hs)
    if places <= 0:
        raise RecruitingError("Your roster for next season is full.")
    if count + 1 > math.floor(places * hs.programs.offer_overcommit):
        raise RecruitingError(f"With {places} places left you can have at most "
                              f"{math.floor(places * hs.programs.offer_overcommit)} offers out.")
    if current is not None and current.status in (rc.DECLINED,) and r.status == rc.OPEN \
            and current.share >= share:
        raise RecruitingError(f"{r.name} turned that down: offer him more.")
    board.offer(recruit_id, user, share)
    row = board.interest_row(recruit_id, user)
    if row.priority is None:
        row.priority, row.changed = rc.WATCH, True
    rc.save_board(conn, board)


def pull_offer(conn: Connection, world: World, meta: CareerMeta, recruit_id: int) -> list[str]:
    """Withdraw the user's offer. Pulling one a recruit committed to (before he signs) frees his
    place and money, and costs the program interest with every recruit it targets. News."""
    board, user = _board(conn, world, meta)
    r = board.recruits.get(recruit_id)
    o = board.offers.get((recruit_id, user))
    if r is None or o is None or o.status not in (rc.OFFERED, rc.ACCEPTED):
        raise RecruitingError("You have no offer out to him.")
    if r.status == rc.SIGNED:
        raise RecruitingError(f"{r.name} has signed with you.")
    news: list[str] = []
    if o.status == rc.ACCEPTED and r.status == rc.COMMITTED:
        board.programs[user].release(r.group, r.share or 0.0, r.overall)
        r.status, r.club_id, r.share, r.committed_on, r.changed = rc.OPEN, None, None, None, True
        penalty = board.hs.user.decommit_penalty
        for row in board.rows_by_club.get(user, {}).values():
            if row.priority is not None and row.recruit_id != recruit_id:
                row.interest, row.changed = max(0.0, row.interest - penalty), True
        news.append(f"You pulled {r.name}'s scholarship. Recruits hear about it: your other "
                    "targets trust you a little less.")
    board.set_offer_status(o, rc.PULLED)
    row = board.interest_row(recruit_id, user)
    row.priority, row.changed = None, True
    rc.save_board(conn, board)
    return news
