"""High-school recruiting for US college soccer (W9c; data/config/college/recruiting.yaml).

- **The class.** On a season's first day the game makes the national class of high-school seniors
  who enroll at the next season's start (``class_season``): made-up players with a position, a
  home state (or a country abroad), a true overall and potential (hidden), and the recruiting
  services' grade, which sets their national, position and state ranks and their stars. They
  aren't players until they enroll, so the many who never sign never reach the save's players.
- **Programs** have a prestige (0-100: from the tier, then moved by results at each rollover),
  scholarship money (full scholarships, by tier: the 2025 rules have no cap) and a roster limit
  of 28. Next season's money and places are what the returning players (this season's
  freshmen to juniors, less those who declared) and the class so far leave.
- **Each week** (Mondays, from August): AI programs offer scholarships to the recruits they can
  hope to land, by need, and spread their staff's effort over their targets; interest grows with
  effort, faster with an offer out, and fades without it. Each recruit scores his offers on the
  money, the program's prestige against what he expects, his playing time at his position, the
  distance from home, the attention he got and his own fit, each weighted by his priorities, and
  commits when ready and one offer is clearly best. A program can't take a commitment it has no
  money or place for: he moves to his next choice.
- **Signing day** (early February) makes every commitment a signing; recruits still open decide
  faster from then. **The class closes** on 1 May: programs still short sign the best left (as
  walk-ons if their money is gone), and the rest leave the game.
- **At the rollover** the signed recruits enroll as freshmen (``enroll_class``).

The user's own program (a college coach's) never recruits by itself: its targets and offers are
the user's (W9c R3). Every draw goes through ``derive_rng`` with the career's seed."""

import json
import math
from bisect import bisect_right
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from weakref import WeakKeyDictionary

import numpy as np
from sqlalchemy import Connection, Engine, select, text

from footsim.core.rng import derive_rng
from footsim.defs.college import DECISION_PARTS, Curve, HsRecruitingDef, StateDef, on
from footsim.domain.attributes import ATTRIBUTES
from footsim.persistence.schema import (
    club,
    college_team,
    nation,
    recruit,
    recruit_interest,
    recruit_offer,
    season,
)
from footsim.world.college.common import ENROLLED, PROSPECT
from footsim.world.college.roster import RecruitPerson, _Maker
from footsim.world.context import World
from footsim.world.lifecycle import _name_pools
from footsim.world.meta import CareerMeta, bump_players_epoch, players_epoch

# A recruit's status.
OPEN = "open"
COMMITTED = "committed"
SIGNED = "signed"
JOINED = "enrolled"
GONE = "gone"
# An offer's.
OFFERED = "open"
PULLED = "pulled"
ACCEPTED = "accepted"
DECLINED = "declined"
# A program's priority on a target.
TOP, HIGH, WATCH = "top", "high", "watch"

STAR_NAMES = {5: "five-star", 4: "four-star", 3: "three-star", 2: "two-star"}


# --- small helpers -------------------------------------------------------------------------


def along(curve: Curve, rank: float) -> float:
    """The curve's value at ``rank``: linear between its points, flat beyond them."""
    if rank <= curve[0][0]:
        return float(curve[0][1])
    for (r0, v0), (r1, v1) in zip(curve, curve[1:], strict=False):
        if rank <= r1:
            return float(v0 + (v1 - v0) * (rank - r0) / (r1 - r0))
    return float(curve[-1][1])


def miles(a: StateDef, b: StateDef) -> float:
    """The great-circle distance between two states' centres."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 3958.8 * 2 * math.asin(math.sqrt(min(1.0, h)))


def step_down(value: float, step: float) -> float:
    """``value`` rounded down to the scholarship step (and never below 0)."""
    return max(0.0, math.floor(value / step + 1e-9) * step)


def step_round(value: float, step: float) -> float:
    return max(0.0, round(value / step) * step)


@dataclass(frozen=True)
class RecruitingDates:
    start: date  # offers begin
    signing_day: date
    close: date  # the class closes


def recruiting_dates(hs: HsRecruitingDef, season_start: date) -> RecruitingDates:
    """The recruiting calendar of the season starting ``season_start`` (its class enrolls at the
    next season's start). Signing day is the first Wednesday on or after its date."""
    signing = on(hs.calendar.signing_day, season_start)
    signing += timedelta(days=(2 - signing.weekday()) % 7)
    return RecruitingDates(on(hs.calendar.start, season_start), signing,
                           on(hs.calendar.close, season_start))


def season_start(conn: Connection, season_id: int) -> date:
    return date.fromisoformat(str(conn.execute(select(season.c.start_date).where(
        season.c.id == season_id)).scalar_one()))


def _next_year(day: date) -> date:
    try:
        return day.replace(year=day.year + 1)
    except ValueError:  # 29 February
        return day.replace(year=day.year + 1, day=28)


def program_states(world: World) -> dict[str, str]:
    """Each program's club name -> its state."""
    return {t.name: t.state for c in world.defs.college.conferences.values() for t in c.teams}


# --- the programs ----------------------------------------------------------------------------


@dataclass
class Program:
    """A program as recruiting sees it: next season's roster and money, and its class so far."""

    club_id: int
    name: str
    tier: int
    state: str
    prestige: float
    funding: float
    effort: float
    returning: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    returning_count: int = 0
    returning_money: float = 0.0
    class_count: int = 0
    class_money: float = 0.0
    class_groups: Counter[str] = field(default_factory=Counter)
    class_overalls: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    visits: int = 0

    def places_left(self, hs: HsRecruitingDef) -> int:
        return hs.programs.roster_max - self.returning_count - self.class_count

    def money_left(self) -> float:
        return self.funding - self.returning_money - self.class_money

    def can_take(self, hs: HsRecruitingDef, share: float) -> bool:
        return self.places_left(hs) >= 1 and self.money_left() + 1e-6 >= share

    def take(self, group: str, share: float, overall: float) -> None:
        self.class_count += 1
        self.class_money += share
        self.class_groups[group] += 1
        self.class_overalls[group].append(overall)

    def release(self, group: str, share: float, overall: float) -> None:
        self.class_count -= 1
        self.class_money -= share
        self.class_groups[group] -= 1
        self.class_overalls[group].remove(overall)


# Each open database's college players' best positions and overalls there, with the
# players_epoch they were worked out at (attributes and positions change only with a bump).
# Dropped with the other caches when a write rolls back (api/session.py).
_OVERALLS: WeakKeyDictionary[Engine, tuple[int, dict[int, tuple[str, float]]]] = (
    WeakKeyDictionary())


def forget_overalls(engine: Engine) -> None:
    _OVERALLS.pop(engine, None)


def _overalls(conn: Connection, world: World) -> dict[int, tuple[str, float]]:
    epoch = players_epoch(conn)
    kept = _OVERALLS.get(conn.engine)
    found: dict[int, tuple[str, float]] = kept[1] if kept and kept[0] == epoch else {}
    missing: Sequence[Any] = conn.execute(text(f"""
        SELECT cp.player_id FROM college_player cp
        WHERE cp.status IN ('{ENROLLED}', '{PROSPECT}')""")).scalars().all()
    wanted = [int(p) for p in missing if int(p) not in found]
    if wanted:
        conn.execute(text("CREATE TEMP TABLE IF NOT EXISTS _wanted_overall "
                          "(player_id INTEGER PRIMARY KEY)"))
        conn.execute(text("DELETE FROM _wanted_overall"))
        conn.execute(text("INSERT INTO _wanted_overall VALUES (:p)"),
                     [{"p": p} for p in wanted])
        rows = conn.execute(text("""
            SELECT a.*, (SELECT position FROM player_position pp
                         WHERE pp.player_id = a.player_id
                         ORDER BY familiarity DESC, position LIMIT 1) AS position
            FROM player_attr a JOIN _wanted_overall w ON w.player_id = a.player_id
            ORDER BY a.player_id""")).all()
        if rows:
            groups = world.model.group_overalls(
                np.array([[getattr(r, a) for a in ATTRIBUTES] for r in rows], dtype=float))
            for i, r in enumerate(rows):
                position = str(r.position or "CM")
                found[int(r.player_id)] = (
                    position, float(groups[world.defs.positions[position].group][i]))
    _OVERALLS[conn.engine] = (epoch, found)
    return found


def college_overalls(conn: Connection, world: World, where: str = "1 = 1",
                     params: dict[str, Any] | None = None) -> list[tuple[Any, str, float]]:
    """Every college player (enrolled or declared) matching ``where`` (on ``cp``), with his
    best position and his overall there."""
    rows = conn.execute(text(f"""
        SELECT cp.player_id, cp.club_id, cp.class_year, cp.status, cp.scholarship
        FROM college_player cp
        WHERE cp.status IN ('{ENROLLED}', '{PROSPECT}') AND {where}
        ORDER BY cp.player_id"""), params or {}).all()
    if not rows:
        return []
    known = _overalls(conn, world)
    return [(r, *known[int(r.player_id)]) for r in rows if int(r.player_id) in known]


def load_programs(conn: Connection, world: World, class_season: int) -> dict[int, Program]:
    """Every program with next season's returning players and ``class_season``'s class so far."""
    hs = world.defs.college.recruiting
    rules = hs.programs
    growth = hs.decision.returning_growth
    states = program_states(world)
    programs: dict[int, Program] = {}
    for r in conn.execute(select(college_team.c.club_id, college_team.c.tier,
                                 college_team.c.prestige, club.c.name)
                          .join(club, club.c.id == college_team.c.club_id)
                          .order_by(college_team.c.club_id)):
        tier = int(r.tier)
        prestige = float(r.prestige) if r.prestige is not None else rules.prestige_by_tier[tier]
        programs[int(r.club_id)] = Program(
            int(r.club_id), str(r.name), tier, states.get(str(r.name), "KS"), prestige,
            rules.funding_by_tier[tier], rules.effort_by_tier[tier])
    positions = world.defs.positions
    for row, position, overall in college_overalls(conn, world):
        p = programs.get(int(row.club_id))
        if p is None or row.status != ENROLLED or int(row.class_year) >= 4:
            continue  # seniors and declared players won't be back
        p.returning[positions[position].group].append(overall + growth)
        p.returning_count += 1
        p.returning_money += float(row.scholarship)
    for group_list in (lst for p in programs.values() for lst in p.returning.values()):
        group_list.sort()
    # The program builder (W9d): money is the limit, set as each program's class budget, and its
    # facilities add to its appeal.
    from footsim.world.college.program import appeal, class_budgets, is_on

    if is_on(conn):
        budgets = class_budgets(conn)
        bonus = appeal(conn, world)
        for p in programs.values():
            p.funding = p.returning_money + budgets.get(p.club_id, 0.0)
            p.prestige += bonus.get(p.club_id, 0.0)
    for r in conn.execute(select(recruit.c.club_id, recruit.c.position, recruit.c.share,
                                 recruit.c.overall)
                          .where(recruit.c.class_season == class_season,
                                 recruit.c.status.in_((COMMITTED, SIGNED)))
                          .order_by(recruit.c.id)):
        p = programs.get(int(r.club_id))
        if p is not None:
            p.take(positions[str(r.position)].group, float(r.share or 0.0), float(r.overall))
    for r in conn.execute(text(
            "SELECT i.club_id, COUNT(*) AS n FROM recruit_interest i JOIN recruit r "
            "ON r.id = i.recruit_id WHERE r.class_season = :c AND i.visited_on IS NOT NULL "
            "GROUP BY i.club_id"), {"c": class_season}):
        if int(r.club_id) in programs:
            programs[int(r.club_id)].visits = int(r.n)
    return programs


def starters(world: World) -> Counter[str]:
    """The starters each position group has in the college roster shape's first eleven."""
    shape = world.defs.college.rules.roster.shape[:11]
    return Counter(world.defs.positions[p].group for p in shape)


def wanted_by_group(world: World) -> Counter[str]:
    """How many players of each group a full roster has (the roster shape, to the target)."""
    hs = world.defs.college.recruiting
    shape = world.defs.college.rules.roster.shape[:hs.programs.roster_target]
    return Counter(world.defs.positions[p].group for p in shape)


# --- starting: prestige, scholarships, the class -----------------------------------------------


def _assign_scholarships(conn: Connection, world: World) -> None:
    """Scholarships for rosters made before recruiting: each program's money spread over its
    players, the better ones getting more (a linear slope, at most a full scholarship each)."""
    hs = world.defs.college.recruiting
    tiers = {int(r.club_id): int(r.tier) for r in conn.execute(
        select(college_team.c.club_id, college_team.c.tier))}
    by_club: dict[int, list[tuple[float, int]]] = defaultdict(list)
    for row, _position, overall in college_overalls(conn, world):
        by_club[int(row.club_id)].append((overall, int(row.player_id)))
    updates = []
    for club_id, players in sorted(by_club.items()):
        players.sort(key=lambda x: (-x[0], x[1]))
        n = len(players)
        raw = [(n - i) / n for i in range(n)]
        funding = min(float(n), hs.programs.funding_by_tier[tiers.get(club_id, 3)])
        low, high = 0.0, 50.0
        for _ in range(40):  # the scale whose capped shares add up to the money
            mid = (low + high) / 2
            if sum(min(1.0, mid * w) for w in raw) < funding:
                low = mid
            else:
                high = mid
        for (_overall, pid), w in zip(players, raw, strict=True):
            share = step_down(min(1.0, high * w), hs.programs.share_step)
            updates.append({"p": pid, "s": round(share, 2)})
    if updates:
        conn.execute(text("UPDATE college_player SET scholarship = :s WHERE player_id = :p"),
                     updates)


def _start_programs(conn: Connection, world: World, meta: CareerMeta) -> None:
    """Prestige and scholarships, the first time a save recruits."""
    hs = world.defs.college.recruiting
    rows = conn.execute(select(college_team.c.club_id, college_team.c.tier, club.c.name)
                        .join(club, club.c.id == college_team.c.club_id)
                        .order_by(college_team.c.club_id)).all()
    updates = []
    for r in rows:
        rng = derive_rng(meta.seed, "college-prestige", str(r.name))
        base = hs.programs.prestige_by_tier[int(r.tier)]
        updates.append({"c": int(r.club_id), "p": round(float(np.clip(
            base + rng.normal(0.0, hs.programs.prestige_sd), 1.0, 99.0)), 2)})
    if updates:
        conn.execute(text("UPDATE college_team SET prestige = :p WHERE club_id = :c"), updates)
    _assign_scholarships(conn, world)


def ensure_recruiting(conn: Connection, world: World, meta: CareerMeta, season_id: int,
                      start: date) -> list[str]:
    """Recruiting for the season starting ``start``: prestige and scholarships the first time,
    then the class that enrolls next season, if it isn't made yet. Returns news."""
    if conn.execute(select(college_team.c.club_id).limit(1)).first() is None:
        return []  # no college world
    if conn.execute(select(college_team.c.club_id).where(
            college_team.c.prestige.is_(None)).limit(1)).first() is not None:
        _start_programs(conn, world, meta)
    class_season = season_id + 1
    if conn.execute(select(recruit.c.id).where(recruit.c.class_season == class_season)
                    .limit(1)).first() is not None:
        return []
    made = make_class(conn, world, meta, class_season, start)
    dates = recruiting_dates(world.defs.college.recruiting, start)
    if meta.user_club_id is None or conn.execute(select(college_team.c.club_id).where(
            college_team.c.club_id == meta.user_club_id)).first() is None:
        return []  # news for a college coach only
    return [f"High-school recruiting: the national class of {made} seniors is ranked. College "
            f"programs can offer scholarships from {dates.start:%-d %B}; signing day is "
            f"{dates.signing_day:%-d %B}."]


def make_class(conn: Connection, world: World, meta: CareerMeta, class_season: int,
               start: date) -> int:
    """The national high-school class that enrolls at ``class_season``'s start, made on
    ``start`` (the season before's first day). Returns its size."""
    hs = world.defs.college.recruiting
    rules = world.defs.college.rules
    ability, grade = hs.ability, hs.grade
    rng = derive_rng(meta.seed, "recruit-class", class_season)
    pools = _name_pools(conn)
    nations = {str(r.name): int(r.id) for r in conn.execute(select(nation.c.id, nation.c.name))}
    home = int(conn.execute(select(nation.c.id).where(nation.c.code == rules.nation))
               .scalar_one())
    foreign = [nations[n] for n in rules.roster.foreign_nations if n in nations]
    codes = sorted(hs.states)
    weights = np.array([hs.states[s].weight for s in codes], dtype=float)
    positions = sorted(hs.positions)
    pos_weights = np.array([hs.positions[p] for p in positions], dtype=float)
    enrolls = _next_year(start)
    low, high = ability.overall_range
    made: list[dict[str, Any]] = []
    for _ in range(hs.class_size):
        abroad = bool(foreign) and rng.random() < hs.international_share
        nation_id = foreign[int(rng.integers(len(foreign)))] if abroad else home
        firsts, lasts = pools.get(nation_id) or pools[None]
        if len(firsts) < 30:
            firsts, lasts = pools[None]
        first = str(firsts[int(rng.integers(len(firsts)))])
        last = str(lasts[int(rng.integers(len(lasts)))])
        state = None if abroad else codes[int(rng.choice(len(codes), p=weights / weights.sum()))]
        position = positions[int(rng.choice(len(positions), p=pos_weights / pos_weights.sum()))]
        overall = float(np.clip(rng.normal(ability.overall, ability.overall_sd), low, high))
        room = max(ability.min_room, float(rng.normal(ability.room, ability.room_sd)))
        if rng.random() < ability.star_share:
            room += float(rng.uniform(*ability.star_bonus))
        potential = int(min(ability.max_potential, max(round(overall + ability.min_room),
                                                       round(overall + room))))
        public = (overall + grade.potential_weight * (potential - overall)
                  + float(rng.normal(0.0, grade.error_sd)))
        age = float(rng.normal(hs.age, hs.age_sd))
        priorities = {part: float(rng.gamma(hs.decision.priority_shape,
                                            1.0 / hs.decision.priority_shape))
                      for part in DECISION_PARTS}
        if not abroad and rng.random() < hs.decision.local_share:
            priorities["home"] *= hs.decision.local_home
        priorities = {k: round(v, 3) for k, v in priorities.items()}
        pace = float(np.clip(rng.normal(1.0, hs.decision.readiness_sd), 0.5, 1.6))
        made.append({
            "class_season": class_season, "first_name": first, "last_name": last,
            "nation_id": nation_id, "state": state, "position": position,
            "birth_date": (enrolls - timedelta(days=int(age * 365.25))).isoformat(),
            "overall": round(overall, 2), "potential": potential, "grade": round(public, 3),
            "priorities": json.dumps(priorities | {"pace": round(pace, 3)}),
            "readiness": 0.0, "status": OPEN})
    order = sorted(range(len(made)), key=lambda i: (-made[i]["grade"], i))
    by_position: Counter[str] = Counter()
    by_state: Counter[str] = Counter()
    for rank, i in enumerate(order, start=1):
        row = made[i]
        row["national_rank"] = rank
        row["stars"] = next((s for s in (5, 4, 3) if rank <= grade.stars[s]), 2)
        by_position[row["position"]] += 1
        row["position_rank"] = by_position[row["position"]]
        if row["state"] is not None:
            by_state[row["state"]] += 1
            row["state_rank"] = by_state[row["state"]]
        else:
            row["state_rank"] = None
    conn.execute(recruit.insert(), [made[i] for i in order])
    return len(made)


# --- a week of recruiting ---------------------------------------------------------------------


@dataclass
class Recruit:
    id: int
    position: str
    group: str
    state: str | None
    overall: float
    grade: float
    stars: int
    national_rank: int
    priorities: dict[str, float]
    readiness: float
    status: str
    club_id: int | None
    share: float | None
    name: str
    expected_prestige: float
    expected_share: float
    committed_on: str | None = None
    signed_on: str | None = None
    potential: int = 0
    position_rank: int = 0
    state_rank: int | None = None
    nation_id: int = 0
    birth_date: str = ""
    changed: bool = False


@dataclass
class Interest:
    recruit_id: int
    club_id: int
    interest: float
    priority: str | None
    knowledge: float
    effort_on: str | None
    visited_on: str | None
    fit: float
    new: bool = False
    changed: bool = False


@dataclass
class Offer:
    recruit_id: int
    club_id: int
    share: float
    made_on: str
    status: str
    new: bool = False
    changed: bool = False


@dataclass
class Board:
    """A class's recruiting state, loaded for a step and written back after it."""

    world: World
    meta: CareerMeta
    class_season: int
    day: date
    programs: dict[int, Program]
    recruits: dict[int, Recruit]
    interest: dict[tuple[int, int], Interest]
    offers: dict[tuple[int, int], Offer]
    news: list[str] = field(default_factory=list)
    # Indexes: offers by recruit and by program, interest rows by program.
    by_recruit: dict[int, dict[int, Offer]] = field(default_factory=lambda: defaultdict(dict))
    by_club: dict[int, dict[int, Offer]] = field(default_factory=lambda: defaultdict(dict))
    rows_by_club: dict[int, dict[int, Interest]] = field(
        default_factory=lambda: defaultdict(dict))

    def __post_init__(self) -> None:
        for (rid, cid), o in self.offers.items():
            self.by_recruit[rid][cid] = o
            self.by_club[cid][rid] = o
        for (rid, cid), row in self.interest.items():
            self.rows_by_club[cid][rid] = row

    @property
    def hs(self) -> HsRecruitingDef:
        return self.world.defs.college.recruiting

    def user_program(self) -> int | None:
        user = self.meta.user_club_id
        return user if user in self.programs else None

    def offers_to(self, recruit_id: int) -> list[Offer]:
        found = self.by_recruit.get(recruit_id)
        return [o for _c, o in sorted(found.items()) if o.status == OFFERED] if found else []

    def interest_row(self, recruit_id: int, club_id: int) -> Interest:
        key = (recruit_id, club_id)
        found = self.interest.get(key)
        if found is None:
            fit = float(derive_rng(self.meta.seed, "recruit-fit", recruit_id, club_id)
                        .normal(0.0, self.hs.decision.fit_sd))
            found = Interest(recruit_id, club_id, 0.0, None, 0.0, None, None, round(fit, 4),
                             new=True)
            self.interest[key] = found
            self.rows_by_club[club_id][recruit_id] = found
        return found

    def offer(self, recruit_id: int, club_id: int, share: float) -> Offer:
        key = (recruit_id, club_id)
        found = self.offers.get(key)
        if found is None:
            found = Offer(recruit_id, club_id, share, self.day.isoformat(), OFFERED, new=True)
            self.offers[key] = found
            self.by_recruit[recruit_id][club_id] = found
            self.by_club[club_id][recruit_id] = found
        else:
            found.share, found.status, found.changed = share, OFFERED, True
            found.made_on = self.day.isoformat()
        self.interest_row(recruit_id, club_id)
        return found

    def set_offer_status(self, o: Offer, status: str) -> None:
        if o.status != status:
            o.status = status
            o.changed = True


def load_board(conn: Connection, world: World, meta: CareerMeta, class_season: int,
               day: date) -> Board:
    hs = world.defs.college.recruiting
    positions = world.defs.positions
    recruits: dict[int, Recruit] = {}
    for r in conn.execute(select(recruit).where(recruit.c.class_season == class_season)
                          .order_by(recruit.c.id)):
        rank = int(r.national_rank)
        recruits[int(r.id)] = Recruit(
            int(r.id), str(r.position), positions[str(r.position)].group, r.state,
            float(r.overall), float(r.grade), int(r.stars), rank, json.loads(r.priorities),
            float(r.readiness), str(r.status),
            int(r.club_id) if r.club_id is not None else None,
            float(r.share) if r.share is not None else None,
            f"{r.first_name} {r.last_name}",
            along(hs.expectations.prestige, rank), along(hs.expectations.share, rank),
            r.committed_on, r.signed_on, int(r.potential), int(r.position_rank),
            int(r.state_rank) if r.state_rank is not None else None, int(r.nation_id),
            str(r.birth_date))
    interest: dict[tuple[int, int], Interest] = {}
    for r in conn.execute(text(
            "SELECT i.* FROM recruit_interest i JOIN recruit r ON r.id = i.recruit_id "
            "WHERE r.class_season = :c"), {"c": class_season}):
        interest[(int(r.recruit_id), int(r.club_id))] = Interest(
            int(r.recruit_id), int(r.club_id), float(r.interest), r.priority,
            float(r.knowledge), r.effort_on, r.visited_on, float(r.fit))
    offers: dict[tuple[int, int], Offer] = {}
    for r in conn.execute(text(
            "SELECT o.* FROM recruit_offer o JOIN recruit r ON r.id = o.recruit_id "
            "WHERE r.class_season = :c"), {"c": class_season}):
        offers[(int(r.recruit_id), int(r.club_id))] = Offer(
            int(r.recruit_id), int(r.club_id), float(r.share), str(r.made_on), str(r.status))
    return Board(world, meta, class_season, day, load_programs(conn, world, class_season),
                 recruits, interest, offers)


def save_board(conn: Connection, board: Board) -> None:
    rec = [{"id": r.id, "readiness": round(r.readiness, 4), "status": r.status,
            "club_id": r.club_id, "share": r.share, "committed_on": r.committed_on,
            "signed_on": r.signed_on} for r in board.recruits.values() if r.changed]
    if rec:
        conn.execute(text("UPDATE recruit SET readiness = :readiness, status = :status, "
                          "club_id = :club_id, share = :share, committed_on = :committed_on, "
                          "signed_on = :signed_on WHERE id = :id"), rec)
    new_rows = [i for i in board.interest.values() if i.new]
    if new_rows:
        conn.execute(recruit_interest.insert(), [
            {"recruit_id": i.recruit_id, "club_id": i.club_id, "interest": round(i.interest, 3),
             "priority": i.priority, "knowledge": round(i.knowledge, 4),
             "effort_on": i.effort_on, "visited_on": i.visited_on, "fit": i.fit}
            for i in new_rows])
    changed = [i for i in board.interest.values() if i.changed and not i.new]
    if changed:
        conn.execute(text(
            "UPDATE recruit_interest SET interest = :interest, priority = :priority, "
            "knowledge = :knowledge, effort_on = :effort_on, visited_on = :visited_on "
            "WHERE recruit_id = :r AND club_id = :c"),
            [{"r": i.recruit_id, "c": i.club_id, "interest": round(i.interest, 3),
              "priority": i.priority, "knowledge": round(i.knowledge, 4),
              "effort_on": i.effort_on, "visited_on": i.visited_on} for i in changed])
    new_offers = [o for o in board.offers.values() if o.new]
    if new_offers:
        conn.execute(recruit_offer.insert(), [
            {"recruit_id": o.recruit_id, "club_id": o.club_id, "share": o.share,
             "made_on": o.made_on, "status": o.status} for o in new_offers])
    changed_offers = [o for o in board.offers.values() if o.changed and not o.new]
    if changed_offers:
        conn.execute(text("UPDATE recruit_offer SET share = :share, made_on = :made_on, "
                          "status = :status WHERE recruit_id = :r AND club_id = :c"),
                     [{"r": o.recruit_id, "c": o.club_id, "share": o.share,
                       "made_on": o.made_on, "status": o.status} for o in changed_offers])


# --- how a recruit scores a program --------------------------------------------------------


def playing_time(board: Board, r: Recruit, p: Program, starters_by_group: Counter[str]) -> float:
    """Where he'd stand at his position group next season: 1 among the starters, less for each
    place below them."""
    ahead_returning = len(p.returning.get(r.group, ())) - bisect_right(
        p.returning.get(r.group, []), r.overall)
    ahead = ahead_returning + _class_ahead(board, r, p)
    places = max(1, starters_by_group.get(r.group, 1))
    if ahead < places:
        return 1.0
    return float(board.hs.decision.bench_decay ** (ahead - places + 1))


def _class_ahead(board: Board, r: Recruit, p: Program) -> int:
    """The program's class so far at his position group who are better than him."""
    return sum(1 for overall in p.class_overalls.get(r.group, ()) if overall > r.overall)


def home_score(board: Board, r: Recruit, p: Program) -> float:
    if r.state is None:
        return 0.5  # from abroad: one program is as far as another
    states = board.hs.states
    return math.exp(-miles(states[r.state], states[p.state]) / board.hs.decision.home_miles)


def prestige_part(board: Board, r: Recruit, p: Program) -> float:
    """How the program's prestige meets what he expects: a half when it matches."""
    return 1.0 / (1.0 + math.exp(-(p.prestige - r.expected_prestige)
                                 / board.hs.decision.prestige_scale))


def parts(board: Board, r: Recruit, p: Program, share: float,
          starters_by_group: Counter[str]) -> dict[str, float]:
    """The five things he weighs about an offer, each 0-1."""
    row = board.interest.get((r.id, p.club_id))
    return {
        "money": min(1.0, share / r.expected_share) if r.expected_share > 0 else 1.0,
        "prestige": prestige_part(board, r, p),
        "playing_time": playing_time(board, r, p, starters_by_group),
        "home": home_score(board, r, p),
        "attention": (row.interest if row else 0.0) / 100.0,
    }


def score(board: Board, r: Recruit, p: Program, share: float,
          starters_by_group: Counter[str]) -> float:
    weights = board.hs.decision.weights
    found = parts(board, r, p, share, starters_by_group)
    row = board.interest.get((r.id, p.club_id))
    return (sum(weights[k] * r.priorities.get(k, 1.0) * v for k, v in found.items())
            + (row.fit if row else 0.0))


# --- the AI programs ---------------------------------------------------------------------------


def _ai_offers(board: Board, after_signing: bool) -> None:
    """Each AI program tops up its offers to the recruits it can hope to land, and pulls them
    once it's full."""
    hs = board.hs
    rules = hs.programs
    wanted = wanted_by_group(board.world)
    user = board.user_program()
    open_recruits = [r for r in board.recruits.values() if r.status == OPEN]
    # The prestige of the programs already offering each recruit, to see how crowded he is.
    rivals: dict[int, list[float]] = {
        r.id: sorted(board.programs[o.club_id].prestige for o in board.offers_to(r.id))
        for r in open_recruits}
    for p in board.programs.values():
        if p.club_id == user:
            continue
        mine = list(board.by_club.get(p.club_id, {}).values())
        open_mine = [o for o in mine if o.status == OFFERED]
        need = min(p.places_left(hs), rules.roster_target - p.returning_count - p.class_count)
        if need <= 0:
            for o in open_mine:
                board.set_offer_status(o, PULLED)
            _ai_priorities(board, p)
            continue
        want = math.ceil(need * rules.offer_overcommit)
        if len(open_mine) >= want or not open_recruits:
            continue
        tried = {o.recruit_id for o in mine}
        rng = derive_rng(board.meta.seed, "recruit-scout", board.class_season, p.club_id)
        # Its scouts' error on each recruit: the same all season (drawn over the whole class,
        # by recruit id, so a recruit's error doesn't move as others commit).
        errors = rng.normal(0.0, rules.ai_error_by_tier[p.tier], max(board.recruits) + 1)
        short = {g: wanted[g] - len(p.returning.get(g, ())) - p.class_groups.get(g, 0)
                 for g in wanted}
        floor = -1e9 if after_signing else p.prestige - rules.ai_floor
        candidates = []
        for r in open_recruits:
            if r.id in tried or r.expected_prestige > p.prestige + rules.ai_reach:
                continue
            if r.expected_prestige < floor:
                continue
            offering = rivals.get(r.id, [])
            stronger = len(offering) - bisect_right(offering, p.prestige - 1e-9)
            value = r.grade + float(errors[r.id]) - rules.crowd_penalty * stronger + (
                rules.need_bonus * min(2, short.get(r.group, 0)) if short.get(r.group, 0) > 0
                else -rules.need_bonus)
            candidates.append((value, r.id, r))
        candidates.sort(key=lambda c: (-c[0], c[1]))
        money = p.money_left() - sum(o.share for o in open_mine) / rules.offer_overcommit
        for _value, _rid, r in candidates[:want - len(open_mine)]:
            share = min(1.0, step_round(r.expected_share, rules.share_step))
            share = min(share, step_down(max(0.0, money), rules.share_step))
            board.offer(r.id, p.club_id, share)
            money -= share / rules.offer_overcommit
        # Its priorities: Top for its best few offers (by grade), High for the rest.
        _ai_priorities(board, p)


def _ai_priorities(board: Board, p: Program) -> None:
    """An AI program's priorities: Top for its best few open offers (by grade), High for the
    rest, and none for a recruit it no longer has an offer out to."""
    live = sorted((o for o in board.by_club.get(p.club_id, {}).values() if o.status == OFFERED),
                  key=lambda o: (-board.recruits[o.recruit_id].grade, o.recruit_id))
    keep: dict[int, str] = {o.recruit_id: TOP if i < board.hs.programs.ai_top_targets else HIGH
                            for i, o in enumerate(live)}
    for row in board.rows_by_club.get(p.club_id, {}).values():
        priority = keep.get(row.recruit_id)
        if row.priority != priority:
            row.priority, row.changed = priority, True
    for rid in keep:
        board.interest_row(rid, p.club_id)
        row = board.interest[(rid, p.club_id)]
        if row.priority != keep[rid]:
            row.priority, row.changed = keep[rid], True


def _ai_close(board: Board) -> None:
    """The class closes: programs still short sign the best left who'll come (as walk-ons once
    the money is gone), the strongest programs choosing first, a recruit at a time."""
    hs = board.hs
    rules = hs.programs
    user = board.user_program()
    left = sorted((r for r in board.recruits.values() if r.status == OPEN),
                  key=lambda r: (-r.grade, r.id))
    order = sorted((p for p in board.programs.values() if p.club_id != user),
                   key=lambda p: (-p.prestige, p.club_id))
    taken: set[int] = set()
    while True:
        signed_any = False
        for p in order:
            if min(p.places_left(hs), rules.roster_target - p.returning_count
                   - p.class_count) <= 0:
                continue
            pick = next((r for r in left if r.id not in taken), None)
            if pick is None:
                break
            share = min(step_round(pick.expected_share, rules.share_step),
                        step_down(p.money_left(), rules.share_step))
            _sign(board, pick, p, share)
            taken.add(pick.id)
            signed_any = True
        if not signed_any:
            break


# --- effort, interest and visits -----------------------------------------------------------------


def _effort(board: Board) -> None:
    """Each program's staff spread their week over its targets by priority; interest grows with
    effort (faster with an offer out) and fades without it; campus visits for Top targets."""
    hs = board.hs
    rules = hs.programs
    today = board.day.isoformat()
    user = board.user_program()
    targets: dict[int, list[Interest]] = defaultdict(list)
    for row in board.interest.values():
        r = board.recruits[row.recruit_id]
        if r.status not in (OPEN, COMMITTED) or (r.status == COMMITTED
                                                 and r.club_id != row.club_id
                                                 and row.club_id != user):
            continue
        if row.priority is not None:
            targets[row.club_id].append(row)
        elif row.interest > 0:
            row.interest *= 1.0 - rules.interest_decay
            row.changed = True
    for club_id, rows in targets.items():
        p = board.programs[club_id]
        total = sum(rules.priority_weight[row.priority or WATCH] for row in rows)
        for row in sorted(rows, key=lambda x: x.recruit_id):
            effort = min(rules.effort_cap,
                         p.effort * rules.priority_weight[row.priority or WATCH] / total)
            offered = (board.offers.get((row.recruit_id, club_id)) is not None
                       and board.offers[(row.recruit_id, club_id)].status == OFFERED)
            gain = effort * rules.interest_gain * (1.0 + (rules.offer_boost if offered else 0.0))
            row.interest = min(100.0, row.interest + gain)
            if club_id == user:
                row.knowledge = min(1.0, row.knowledge + effort * rules.scouting_gain)
            row.effort_on = today
            row.changed = True
            if (row.priority == TOP and offered and row.visited_on is None
                    and row.interest >= rules.visit_interest and p.visits < rules.official_visits
                    and board.recruits[row.recruit_id].status == OPEN
                    # one invited to a game day visits then (world/college/visits.py)
                    and not (club_id == user and row.recruit_id in board.meta.gameday_visits)):
                row.interest = min(100.0, row.interest + rules.visit_boost)
                row.visited_on = today
                p.visits += 1
                if club_id == user:
                    board.news.append(f"{board.recruits[row.recruit_id].name} visits campus.")


# --- decisions -----------------------------------------------------------------------------------


def _commit(board: Board, r: Recruit, p: Program, share: float, signed: bool) -> None:
    r.status = SIGNED if signed else COMMITTED
    r.club_id, r.share, r.changed = p.club_id, share, True
    r.committed_on = board.day.isoformat()
    r.signed_on = board.day.isoformat() if signed else None
    r.readiness = max(r.readiness, 1.0)
    p.take(r.group, share, r.overall)
    for o in board.offers_to(r.id):
        board.set_offer_status(o, ACCEPTED if o.club_id == p.club_id else DECLINED)
    _announce(board, r, p, "signs with" if signed else "commits to")


def _sign(board: Board, r: Recruit, p: Program, share: float) -> None:
    """A late signing at the class's close (no offer needed)."""
    key = (r.id, p.club_id)
    if key not in board.offers:
        board.offer(r.id, p.club_id, share)
    else:
        board.offers[key].share = share
        board.set_offer_status(board.offers[key], OFFERED)
    _commit(board, r, p, share, signed=True)


def _announce(board: Board, r: Recruit, p: Program, verb: str) -> None:
    user = board.user_program()
    if p.club_id == user:
        board.news.append(f"{r.name} ({STAR_NAMES[r.stars]}, No. {r.national_rank} nationally, "
                          f"{r.position}) {verb} {p.name}.")
    elif user is not None and (r.id, user) in board.interest and \
            board.interest[(r.id, user)].priority is not None:
        board.news.append(f"Your target {r.name} {verb} {p.name}.")
    elif r.national_rank <= 10:
        board.news.append(f"The No. {r.national_rank} recruit, {r.name} ({r.position}), "
                          f"{verb} {p.name}.")


def _choices(board: Board, r: Recruit, starters_by_group: Counter[str]
             ) -> list[tuple[float, Offer]]:
    found = [(score(board, r, board.programs[o.club_id], o.share, starters_by_group), o)
             for o in board.offers_to(r.id) if o.club_id in board.programs]
    return sorted(found, key=lambda x: (-x[0], x[1].club_id))


def _decide(board: Board, r: Recruit, starters_by_group: Counter[str], now: bool,
            signing: bool) -> None:
    """An open recruit decides if he's ready (or ``now``): the best offer whose program can take
    him, if it is clearly best (or ``now``). Offers that can't be honoured are declined."""
    hs = board.hs
    if not now and r.readiness < 1.0:
        return
    choices = _choices(board, r, starters_by_group)
    while choices:
        best_score, best = choices[0]
        p = board.programs[best.club_id]
        if not p.can_take(hs, best.share):
            board.set_offer_status(best, DECLINED)
            if p.club_id == board.user_program():
                why = "place" if p.places_left(hs) < 1 else "scholarship money"
                board.news.append(f"{r.name} wanted to commit to you, but you have no "
                                  f"{why} left for him: he's looking elsewhere.")
            choices.pop(0)
            continue
        runner_up = choices[1][0] if len(choices) > 1 else -1e9
        if now or r.readiness >= 2.0 or best_score - runner_up >= hs.decision.margin:
            _commit(board, r, p, best.share, signed=signing)
        return


def _maybe_flip(board: Board, r: Recruit, starters_by_group: Counter[str]) -> None:
    """A committed recruit may flip, before signing day, to a much better newer offer."""
    hs = board.hs
    assert r.club_id is not None
    current = board.programs.get(r.club_id)
    rivals = [(s, o) for s, o in _choices(board, r, starters_by_group) if o.club_id != r.club_id]
    if current is None or not rivals:
        return
    mine = score(board, r, current, r.share or 0.0, starters_by_group)
    best_score, best = rivals[0]
    other = board.programs[best.club_id]
    if best_score - mine < hs.decision.flip_margin or not other.can_take(hs, best.share):
        return
    if derive_rng(board.meta.seed, "recruit-flip", r.id, board.day.isoformat()).random() \
            >= hs.decision.flip_chance:
        return
    current.release(r.group, r.share or 0.0, r.overall)
    old = (r.id, current.club_id)
    if old in board.offers:
        board.set_offer_status(board.offers[old], DECLINED)
    _announce(board, r, current, "decommits from")
    _commit(board, r, other, best.share, signed=False)


def _decisions(board: Board, after_signing: bool) -> None:
    hs = board.hs
    starters_by_group = starters(board.world)
    for r in board.recruits.values():  # by id
        if r.status == OPEN:
            offers = board.offers_to(r.id)
            if offers:
                pace = hs.decision.readiness[r.stars] * r.priorities.get("pace", 1.0)
                best = max(prestige_part(board, r, board.programs[o.club_id]) for o in offers)
                pace *= hs.decision.waiting["base"] + hs.decision.waiting["weight"] * best
                r.readiness += pace * (hs.decision.late_pace if after_signing else 1.0)
                r.changed = True
            _decide(board, r, starters_by_group, now=False, signing=after_signing)
        elif r.status == COMMITTED and not after_signing:
            _maybe_flip(board, r, starters_by_group)


def _signing_day(board: Board) -> None:
    """Every commitment becomes a signing; recruits still open with an offer they can take
    decide today."""
    starters_by_group = starters(board.world)
    signed = 0
    user = board.user_program()
    for r in board.recruits.values():
        if r.status == COMMITTED:
            r.status, r.signed_on, r.changed = SIGNED, board.day.isoformat(), True
            signed += 1
    for r in board.recruits.values():
        if r.status == OPEN and board.offers_to(r.id):
            _decide(board, r, starters_by_group, now=True, signing=True)
            signed += r.status == SIGNED
    if user is not None:
        mine = sum(1 for r in board.recruits.values()
                   if r.club_id == user and r.status == SIGNED)
        board.news.append(f"Signing day: {mine} recruits sign with "
                          f"{board.programs[user].name}.")
    board.news.append(f"Signing day: {signed} high-school seniors sign with college programs.")


def _close(board: Board) -> None:
    """The class closes: the AI programs' last places, and the rest leave the game."""
    _ai_close(board)
    gone = 0
    for r in board.recruits.values():
        if r.status == OPEN:
            r.status, r.changed = GONE, True
            gone += 1
        if r.status == COMMITTED:  # (none after signing day; for safety)
            r.status, r.signed_on, r.changed = SIGNED, board.day.isoformat(), True
    for o in board.offers.values():
        if o.status == OFFERED:
            board.set_offer_status(o, DECLINED)
    board.news.append(f"The recruiting class closes: {gone} unsigned seniors go to Division II, "
                      "NAIA or junior college.")


def progress_recruiting(conn: Connection, world: World, meta: CareerMeta, day: date
                        ) -> list[str]:
    """A day of recruiting for the class enrolling next season: the weekly step on Mondays,
    signing day and the class's close. Returns news."""
    class_season = meta.season_id + 1
    hs = world.defs.college.recruiting
    if conn.execute(select(recruit.c.id).where(recruit.c.class_season == class_season)
                    .limit(1)).first() is None:
        return []
    dates = recruiting_dates(hs, season_start(conn, meta.season_id))
    weekly = day.weekday() == 0 and dates.start <= day < dates.close
    if not (weekly or day in (dates.signing_day, dates.close)):
        return []
    board = load_board(conn, world, meta, class_season, day)
    if day == dates.close:
        _close(board)
    else:
        if weekly:
            _ai_offers(board, after_signing=day > dates.signing_day)
            _effort(board)
            _decisions(board, after_signing=day > dates.signing_day)
        if day == dates.signing_day:
            _signing_day(board)
    save_board(conn, board)
    # Recruiting is news for a college coach; a professional club's manager sees it on the
    # College page.
    return board.news if board.user_program() is not None else []


# --- the rollover --------------------------------------------------------------------------------


def enroll_class(conn: Connection, world: World, meta: CareerMeta, season_id: int,
                 day: date) -> int:
    """The signed recruits of the class enrolling at ``season_id``'s start join their programs as
    freshmen; any still open leave the game. Returns how many enrolled."""
    rows = conn.execute(select(recruit, club.c.reputation)
                        .join(club, club.c.id == recruit.c.club_id)
                        .where(recruit.c.class_season == season_id,
                               recruit.c.status == SIGNED)
                        .order_by(recruit.c.id)).all()
    conn.execute(text("UPDATE recruit SET status = :gone WHERE class_season = :c "
                      "AND status IN (:open, :committed)"),
                 {"gone": GONE, "c": season_id, "open": OPEN, "committed": COMMITTED})
    # Portal players (W9e) are players already: they move up from their D-II/D-III school.
    portal = [r for r in rows if r.player_id is not None]
    rows = [r for r in rows if r.player_id is None]
    if portal:
        from footsim.world.college.lower import move_up  # lower imports college.season

        for r in portal:
            move_up(conn, season_id, day, int(r.player_id), int(r.club_id),
                    float(r.share or 0.0))
        conn.execute(text(f"UPDATE recruit SET status = '{JOINED}' WHERE id = :id"),
                     [{"id": int(r.id)} for r in portal])
        bump_players_epoch(conn)
    if not rows:
        return len(portal)
    maker = _Maker(conn, world, meta, day)
    links = []
    for r in rows:
        born = date.fromisoformat(r.birth_date)
        age = (day - born).days / 365.25
        pid = maker.make(int(r.club_id), int(r.reputation), str(r.position), 1, age,
                         float(r.overall), season_id,
                         signed=RecruitPerson(str(r.first_name), str(r.last_name),
                                              int(r.nation_id), born, int(r.potential)),
                         scholarship=float(r.share or 0.0))
        links.append({"id": int(r.id), "p": pid})
    maker.rows.write(conn, with_state=True)
    conn.execute(text(f"UPDATE recruit SET status = '{JOINED}', player_id = :p WHERE id = :id"),
                 links)
    bump_players_epoch(conn)
    return len(rows) + len(portal)


def had_class(conn: Connection, season_id: int) -> bool:
    """Whether the class enrolling at ``season_id``'s start was recruited (not generated)."""
    return conn.execute(select(recruit.c.id).where(recruit.c.class_season == season_id)
                        .limit(1)).first() is not None


def update_prestige(conn: Connection, world: World, meta: CareerMeta, old_season: int
                    ) -> None:
    """Each program's prestige moves towards a target from its tier and its last seasons:
    its RPI rank, NCAA tournament wins and the national title."""
    from footsim.world.college.season import NATIONAL_TITLE, college_competition, rankings

    hs = world.defs.college.recruiting
    rules = hs.programs
    comp = college_competition(conn, world)
    rows = conn.execute(select(college_team.c.club_id, college_team.c.tier,
                               college_team.c.prestige)).all()
    if comp is None or not rows or any(r.prestige is None for r in rows):
        return
    seasons = [s for s in range(old_season - rules.results_seasons + 1, old_season + 1) if s >= 1]
    success: dict[int, list[float]] = defaultdict(list)
    for s in seasons:
        rpi = rankings(conn, world, s)
        if not rpi:
            continue
        order = sorted(rpi, key=lambda c: (-rpi[c], c))
        n = len(order)
        wins: Counter[int] = Counter()
        for r in conn.execute(text(
                "SELECT home_club_id, away_club_id, home_goals, away_goals, home_pens, "
                "away_pens FROM fixture WHERE season_id = :s AND competition_id = :c "
                "AND stage = 'NCAA' AND status = 'played'"), {"s": s, "c": comp}):
            home = (r.home_goals, r.home_pens or 0) > (r.away_goals, r.away_pens or 0)
            wins[int(r.home_club_id if home else r.away_club_id)] += 1
        champion = conn.execute(text(
            "SELECT club_id FROM league_title WHERE season_id = :s AND competition_id = :c "
            "AND title = :t"), {"s": s, "c": comp, "t": NATIONAL_TITLE}).scalar()
        for i, club_id in enumerate(order):
            value = 100.0 * (1.0 - i / max(1, n - 1)) + rules.ncaa_win_points * wins[club_id]
            if champion is not None and int(champion) == club_id:
                value += rules.title_points
            success[club_id].append(min(100.0, value))
    updates = []
    for r in rows:
        results = success.get(int(r.club_id))
        if not results:
            continue
        base = rules.prestige_by_tier[int(r.tier)]
        target = (1 - rules.results_weight) * base + rules.results_weight * float(
            np.mean(results))
        prestige = float(r.prestige) + rules.prestige_rate * (target - float(r.prestige))
        updates.append({"c": int(r.club_id), "p": round(float(np.clip(prestige, 1, 99)), 2)})
    if updates:
        conn.execute(text("UPDATE college_team SET prestige = :p WHERE club_id = :c"), updates)
        # The club's reputation follows: the tiers' reputations at the tiers' prestiges.
        reputations = world.defs.college.rules.roster.reputation_by_tier
        curve = sorted((rules.prestige_by_tier[t], float(reputations[t])) for t in reputations)
        conn.execute(text("UPDATE club SET reputation = :r WHERE id = :c"),
                     [{"c": u["c"], "r": round(along(curve, u["p"]))} for u in updates])
