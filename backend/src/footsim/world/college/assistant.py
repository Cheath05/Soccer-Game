"""The recruiting assistant (20 Nov; reworked 22 Nov): with the setting on, a college coach's
staff recruit next season's squad.

Every Monday from the day offers open until signing day (and when the setting is switched on) it
counts next season's squad at each position group: the players staying (not the seniors, those
who declared for the draft, or those likely to declare early) and the class committed. Against
a balanced roster (``targets``: the first ``roster_target`` positions of the roster shape), each
group still short gets about ``assistant.overcommit`` offers out for each place, to the best
realistic recruits at it (a good fit or a reach for the program's prestige; the best by the
staff's estimate of their potential, then by national rank), each a Top target offered the
scholarship he hopes for. Where a group is covered, or more is out than it needs, it pulls its
own offers still open (remembered in ``assistant_offers``), the least wanted first; never the
coach's own offers or targets. It stops where the program's money or places run out.

Until 22 Nov it replaced leavers one for one with twice the offers and never pulled any, so a
position where every offer was accepted ended up with twice the players it needed, and a squad
already short somewhere got no help (the user's save: six midfielders for three places)."""

import math
from collections import Counter
from datetime import date

from sqlalchemy import Connection, text

from footsim.world.college import coach
from footsim.world.college import recruiting as rc
from footsim.world.college.common import ENROLLED, PROSPECT, is_college_club
from footsim.world.context import World
from footsim.world.meta import CareerMeta, write_meta

REALISTIC = ("good", "reach")


def leaving(conn: Connection, world: World, meta: CareerMeta) -> Counter[str]:
    """The user's players leaving after this season, by position group: the seniors, those who
    declared for the draft, and those likely to declare early (the draft watch, stay.py)."""
    from footsim.world.college.stay import LIKELY, draft_watch

    likely = {p for p, risk in draft_watch(conn, world, meta).items() if risk == LIKELY}
    found: Counter[str] = Counter()
    for r in conn.execute(text(
            "SELECT cp.player_id, cp.status, cp.class_year, (SELECT position FROM player_position "
            "pp WHERE pp.player_id = cp.player_id ORDER BY familiarity DESC, position LIMIT 1) "
            "AS position FROM college_player cp WHERE cp.club_id = :c AND cp.status IN (:e, :p)"),
            {"c": meta.user_club_id, "e": ENROLLED, "p": PROSPECT}):
        if not (r.status == PROSPECT or r.class_year >= 4 or int(r.player_id) in likely):
            continue
        if r.position in world.defs.positions:
            found[str(world.defs.positions[r.position].group)] += 1
    return found


def _group(world: World, position: str) -> str:
    return str(world.defs.positions[position].group)


def targets(world: World) -> Counter[str]:
    """A balanced roster by position group: the first ``roster_target`` positions of the roster
    shape (rules.yaml)."""
    college = world.defs.college
    shape = college.rules.roster.shape[:college.recruiting.programs.roster_target]
    return Counter(_group(world, p) for p in shape if p in world.defs.positions)


def next_season(conn: Connection, world: World, meta: CareerMeta) -> Counter[str]:
    """The user's squad next season by position group: the players staying (not seniors, not
    declared, not likely to declare early) and the recruits committed or signed."""
    from footsim.world.college.stay import LIKELY, draft_watch

    likely = {p for p, risk in draft_watch(conn, world, meta).items() if risk == LIKELY}
    found: Counter[str] = Counter()
    for r in conn.execute(text(
            "SELECT cp.player_id, cp.status, cp.class_year, (SELECT position FROM player_position "
            "pp WHERE pp.player_id = cp.player_id ORDER BY familiarity DESC, position LIMIT 1) "
            "AS position FROM college_player cp WHERE cp.club_id = :c AND cp.status IN (:e, :p)"),
            {"c": meta.user_club_id, "e": ENROLLED, "p": PROSPECT}):
        if r.status == PROSPECT or r.class_year >= 4 or int(r.player_id) in likely:
            continue
        if r.position in world.defs.positions:
            found[_group(world, str(r.position))] += 1
    for r in conn.execute(text(
            "SELECT position FROM recruit WHERE class_season = :s AND club_id = :c "
            "AND status IN (:committed, :signed)"),
            {"s": meta.season_id + 1, "c": meta.user_club_id, "committed": rc.COMMITTED,
             "signed": rc.SIGNED}):
        if r.position in world.defs.positions:
            found[_group(world, str(r.position))] += 1
    return found


def places_left(conn: Connection, world: World, meta: CareerMeta) -> int:
    """The roster places next season not yet taken by the players staying and the class."""
    return world.defs.college.recruiting.programs.roster_max - sum(
        next_season(conn, world, meta).values())


def needs(conn: Connection, world: World, meta: CareerMeta) -> Counter[str]:
    """The places still short at each position group next season (a balanced roster less the
    players staying and the class committed); none where it's covered."""
    have = next_season(conn, world, meta)
    return Counter({g: n - have[g] for g, n in targets(world).items() if n > have[g]})


def recruit_for_leavers(conn: Connection, world: World, meta: CareerMeta, day: date
                        ) -> list[str]:
    """One step of the assistant's recruiting: offers where next season is short, its own open
    offers pulled where it's covered. Returns news."""
    user = meta.user_club_id
    if not meta.auto_recruiting or user is None or not is_college_club(conn, user):
        return []
    stage, _ = coach.phase(world, conn, meta)
    if stage != coach.PHASE_OPEN:
        return []
    short = needs(conn, world, meta)
    views = coach.recruits(conn, world, meta)
    by_id = {v.id: v for v in views}
    # Its own offers still open, the rest forgotten (taken, declined or pulled since).
    mine = [r for r in meta.assistant_offers
            if r in by_id and by_id[r].offer_status == "open" and by_id[r].status == rc.OPEN]
    offered: Counter[str] = Counter()
    for v in views:
        if v.offer_status == "open" and v.status == rc.OPEN:
            offered[_group(world, v.position)] += 1
    overcommit = world.defs.college.recruiting.assistant.overcommit
    step = world.defs.college.recruiting.programs.share_step
    made: list[str] = []
    pulled: list[str] = []
    groups = set(targets(world)) | set(offered)
    want = {g: math.ceil(short[g] * overcommit) if short[g] > 0 else 0 for g in groups}
    # First its surplus: where a group is covered, or more is out than it needs, its own offers
    # still open, the least wanted first.
    for group in sorted(groups):
        extra = offered[group] - want[group]
        if extra <= 0:
            continue
        own = sorted((by_id[r] for r in mine if _group(world, by_id[r].position) == group),
                     key=lambda v: ((v.potential.low + v.potential.high), -v.national_rank))
        for v in own[:extra]:
            try:
                coach.pull_offer(conn, world, meta, v.id)
            except coach.RecruitingError:
                continue
            mine.remove(v.id)
            offered[group] -= 1
            pulled.append(f"{v.name} ({v.position})")
    # Then the gaps, the biggest first, while the program's money and places last.
    for group in sorted(groups, key=lambda g: (-short[g], g)):
        if want[group] - offered[group] <= 0:
            continue
        candidates = sorted(
            (v for v in views if v.status == rc.OPEN and v.fit in REALISTIC
             and v.offer_status is None and v.priority is None
             and _group(world, v.position) == group),
            key=lambda v: (-(v.potential.low + v.potential.high), v.national_rank))
        for v in candidates[:want[group] - offered[group]]:
            share = min(1.0, max(step, round(round(v.hopes / step) * step, 2)))
            try:
                coach.set_target(conn, world, meta, v.id, rc.TOP)
                coach.make_offer(conn, world, meta, v.id, share)
            except coach.RecruitingError:
                coach.set_target(conn, world, meta, v.id, None)
                break  # out of money or places for now
            mine.append(v.id)
            made.append(f"{v.name} ({v.position}, {scholarship_words(share)})")
    # Kept for next time: its open offers, and those that became commitments (pulled no more).
    meta.assistant_offers = sorted(set(mine))
    write_meta(conn, meta)
    news = []
    if made:
        news.append("Your assistant offered scholarships where next season's squad is short: "
                    f"{', '.join(made)}.")
    if pulled:
        news.append("Your assistant withdrew offers at positions now covered: "
                    f"{', '.join(pulled)}.")
    return news


def scholarship_words(share: float) -> str:
    return "full scholarship" if share >= 0.999 else f"{round(share * 100)}%"


def weekly(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """The assistant's Monday."""
    if day.weekday() != 0:
        return []
    return recruit_for_leavers(conn, world, meta, day)
