"""The college world: its programs and their generated rosters, and each season's freshmen.

The programs and conferences are real (data/config/college/ncaa_d1.yaml); the players are made
up, the W7 way (importers/synthetic.py): a player's attributes are copied from a professional of
his position near the overall wanted and shifted to it, his name drawn from the save's own
players of his country (most are American; about a fifth are international). A program's level
comes from its tier, so the traditional powers are stronger and recruit better. Each class sits
about the program's level (seniors above, freshmen below), each player about his class's. Ratings
are calibrated so the best college players sit about 55-62 and a typical starter 45-52
(data/config/college/rules.yaml). Everything is drawn from the career's seed.

A save without the college world gets it at the start of its next season (``ensure_college``),
as ``ensure_leagues`` adds leagues: a new career at its start, an older one at its rollover."""

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
from sqlalchemy import Connection, select, text

from footsim.core.rng import derive_rng
from footsim.defs.college import CollegeRulesDef
from footsim.domain.attributes import ATTRIBUTES
from footsim.importers.generate import (
    draw_personality,
    estimate_height,
    estimate_weight,
    player_reputation,
)
from footsim.persistence.schema import (
    club,
    college_player,
    college_team,
    competition,
    contract,
    nation,
    person,
    player,
    player_attr,
    player_personality,
    player_position,
    player_state,
    tactic,
)
from footsim.world.college.common import COLLEGE_CONTRACT, ENROLLED, IN_COLLEGE_SQL
from footsim.world.context import World, default_instructions
from footsim.world.lifecycle import _name_pools
from footsim.world.meta import CareerMeta, bump_players_epoch


@dataclass(frozen=True)
class _Template:
    overall: float
    attrs: dict[str, int]
    positions: dict[str, int]  # familiarity by position
    foot: str
    weak_foot: int
    skill_moves: int


class Templates:
    """The save's professionals by primary position, to copy attributes from (as
    importers/synthetic.py's Templates does with FC 27's players at a world's build)."""

    def __init__(self, conn: Connection, world: World, pool: int) -> None:
        self.pool = pool
        rows = conn.execute(text(f"""
            SELECT a.*, pl.preferred_foot, pl.weak_foot, pl.skill_moves FROM player_attr a
            JOIN player pl ON pl.person_id = a.player_id
            WHERE pl.retired_on IS NULL AND a.player_id NOT IN ({IN_COLLEGE_SQL})
            ORDER BY a.player_id""")).all()
        familiarity: dict[int, dict[str, int]] = defaultdict(dict)
        for r in conn.execute(select(player_position).order_by(player_position.c.player_id,
                                                                player_position.c.position)):
            familiarity[int(r.player_id)][str(r.position)] = int(r.familiarity)
        matrix = np.array([[getattr(r, a) for a in ATTRIBUTES] for r in rows], dtype=float)
        groups = world.model.group_overalls(matrix) if len(rows) else {}
        self.by_position: dict[str, list[_Template]] = defaultdict(list)
        for i, r in enumerate(rows):
            fams = familiarity.get(int(r.player_id))
            if not fams:
                continue
            position = max(sorted(fams), key=lambda p: fams[p])
            overall = float(groups[world.defs.positions[position].group][i])
            self.by_position[position].append(_Template(
                overall, {a: int(getattr(r, a)) for a in ATTRIBUTES}, dict(fams),
                str(r.preferred_foot), int(r.weak_foot), int(r.skill_moves)))
        self.keys: dict[str, np.ndarray] = {}
        for position, group in self.by_position.items():
            group.sort(key=lambda t: t.overall)
            self.keys[position] = np.array([t.overall for t in group], dtype=float)

    def pick(self, position: str, overall: float, rng: np.random.Generator) -> _Template:
        found = position if self.by_position.get(position) else "CM"
        nearest = np.argsort(np.abs(self.keys[found] - overall), kind="stable")[:self.pool]
        return self.by_position[found][int(nearest[rng.integers(len(nearest))])]


@dataclass
class _Rows:
    """New players' rows, by table, and the overalls their potentials are drawn from."""

    tables: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    count: int = 0

    def write(self, conn: Connection, with_state: bool) -> None:
        tables = [(person, "person"), (player, "player"), (player_attr, "attr"),
                  (player_position, "position"), (player_personality, "personality"),
                  (contract, "contract"), (college_player, "college")]
        if with_state:
            tables.append((player_state, "state"))
        for table, key in tables:
            if self.tables[key]:
                conn.execute(table.insert(), self.tables[key])


class _Maker:
    """Makes college players: one at a time, each from its own random stream."""

    def __init__(self, conn: Connection, world: World, meta: CareerMeta, day: date) -> None:
        self.world, self.meta, self.day = world, meta, day
        self.rules: CollegeRulesDef = world.defs.college.rules
        self.templates = Templates(conn, world, self.rules.roster.template_pool)
        self.pools = _name_pools(conn)
        nations = {r.name: int(r.id) for r in conn.execute(select(nation.c.id, nation.c.name))}
        self.home = int(conn.execute(select(nation.c.id).where(
            nation.c.code == self.rules.nation)).scalar_one())
        self.foreign = [nations[n] for n in self.rules.roster.foreign_nations if n in nations]
        self.next_id = int(conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM person"))
                           .scalar_one()) + 1
        self.rows = _Rows()

    def _names(self, nation_id: int, rng: np.random.Generator) -> tuple[str, str]:
        firsts, lasts = self.pools.get(nation_id) or self.pools[None]
        if len(firsts) < 30:
            firsts, lasts = self.pools[None]
        first = str(firsts[int(rng.integers(len(firsts)))])
        return first, str(lasts[int(rng.integers(len(lasts)))])

    def make(self, club_id: int, club_rep: int, position: str, class_year: int, age: float,
             overall: float, season_id: int) -> int:
        """A player of ``class_year`` aged ``age`` on the day, about ``overall``; his id."""
        pid = self.next_id
        self.next_id += 1
        rng = derive_rng(self.meta.seed, "college-player", pid)
        roster, potential = self.rules.roster, self.rules.potential
        template = self.templates.pick(position, overall, rng)
        shift = overall - template.overall
        values = {a: int(min(99, max(1, round(v + shift)))) for a, v in template.attrs.items()}
        attrs = np.array([[values[a] for a in ATTRIBUTES]], dtype=float)
        own = float(self.world.model.group_overalls(attrs)[
            self.world.defs.positions[position].group][0])
        nation_id = (self.foreign[int(rng.integers(len(self.foreign)))]
                     if self.foreign and rng.random() < roster.foreign_share else self.home)
        first, last = self._names(nation_id, rng)
        born = self.day - timedelta(days=int(age * 365.25))
        room = max(potential.min_room, float(rng.normal(potential.room_by_class[class_year],
                                                        potential.room_sd)))
        if rng.random() < potential.star_share:
            room += float(rng.uniform(*potential.star_bonus))
        pa = int(min(potential.max_potential, max(round(own + potential.min_room),
                                                  round(own + room))))
        build = self.world.defs.world_build
        height = estimate_height(position, values, build.physique, rng)
        fams = dict(template.positions)
        top = max(fams.values())
        fams = {p: f for p, f in fams.items() if p != position and f < top} | {position: top}
        rows = self.rows.tables
        rows["person"].append({"id": pid, "first_name": first, "last_name": last,
                               "known_as": None, "birth_date": born.isoformat(),
                               "nation_id": nation_id, "birth_city": None})
        rows["player"].append({
            "person_id": pid, "height_cm": height,
            "weight_kg": estimate_weight(height, values, build.physique, rng),
            "preferred_foot": template.foot, "weak_foot": template.weak_foot,
            "skill_moves": template.skill_moves, "pa_hidden": pa,
            "reputation": player_reputation(own, club_rep, build.reputation),
            "value_eur_cents": None, "retired_on": None})
        rows["attr"].append({"player_id": pid, **values})
        rows["position"] += [{"player_id": pid, "position": p, "familiarity": f}
                             for p, f in sorted(fams.items())]
        rows["personality"].append({"player_id": pid,
                                    **draw_personality(own, build.personality, rng)})
        graduates = date(self.day.year + (4 - class_year) + 1, 6, 30)
        rows["contract"].append({
            "person_id": pid, "club_id": club_id, "kind": COLLEGE_CONTRACT,
            "start_date": self.day.isoformat(), "end_date": graduates.isoformat(),
            "wage_weekly_cents": 0, "release_clause_cents": None, "is_active": 1})
        rows["college"].append({"player_id": pid, "club_id": club_id, "class_year": class_year,
                                "status": ENROLLED, "ga": 0,
                                "entered_season": season_id - class_year + 1,
                                "declared_season": None, "left_on": None})
        rows["state"].append({"player_id": pid, "condition": 100.0, "form": 6.5,
                              "suspended_matches": 0, "season_yellows": 0})
        self.rows.count += 1
        return pid


def _draw_class(rules: CollegeRulesDef, rng: np.random.Generator) -> int:
    shares = rules.roster.class_shares
    years = sorted(shares)
    weights = np.array([shares[y] for y in years], dtype=float)
    return int(years[int(rng.choice(len(years), p=weights / weights.sum()))])


def _age(rules: CollegeRulesDef, mean: float, sd: float, rng: np.random.Generator) -> float:
    low, high = rules.roster.age_range
    return float(np.clip(rng.normal(mean, sd), low, high))


def _player_overall(rules: CollegeRulesDef, level: float, class_year: int,
                    rng: np.random.Generator) -> float:
    roster = rules.roster
    spread = float(np.clip(rng.normal(0.0, 1.0), -roster.player_sd_cap, roster.player_sd_cap))
    return level + roster.class_offset[class_year] + spread * roster.player_sd


def ensure_college(conn: Connection, world: World, meta: CareerMeta, season_id: int,
                   day: date) -> list[str]:
    """The college world, if the save hasn't got it: its competition, programs and rosters.
    Returns news."""
    rules = world.defs.college.rules
    if conn.execute(select(competition.c.id).where(competition.c.key == rules.key)).first():
        return []
    maker = _Maker(conn, world, meta, day)
    conn.execute(competition.insert().values(
        key=rules.key, name=rules.name, short_name=rules.short_name, nation_id=maker.home,
        type="college", tier=None, sim_level="simulated"))
    instructions = json.dumps(default_instructions(world.defs))
    programs = 0
    for key, conference in world.defs.college.conferences.items():
        for team in conference.teams:
            rng = derive_rng(meta.seed, "college-program", team.name)
            level = rules.roster.level_by_tier[team.tier] + float(
                rng.normal(0.0, rules.roster.level_sd))
            reputation = rules.roster.reputation_by_tier[team.tier]
            inserted = conn.execute(club.insert().values(
                name=team.name, nation_id=maker.home, source_league=rules.source_league,
                reputation=reputation, stadium_name=None, stadium_capacity=None))
            assert inserted.inserted_primary_key is not None
            club_id = int(inserted.inserted_primary_key[0])
            conn.execute(college_team.insert().values(club_id=club_id, conference=key,
                                                      tier=team.tier, level=round(level, 2)))
            conn.execute(tactic.insert().values(club_id=club_id, formation=rules.formation,
                                                roles=json.dumps({}), lineup=None,
                                                instructions=instructions))
            size = int(rng.integers(rules.roster.size[0], rules.roster.size[1] + 1))
            for position in rules.roster.shape[:size]:
                year = _draw_class(rules, rng)
                maker.make(club_id, reputation, position, year,
                           _age(rules, rules.roster.age[year], rules.roster.age_sd, rng),
                           _player_overall(rules, level, year, rng), season_id)
            programs += 1
    maker.rows.write(conn, with_state=True)
    bump_players_epoch(conn)
    return [f"US college soccer: {programs} NCAA Division I programs in "
            f"{len(world.defs.college.conferences)} conferences play from August to the "
            "College Cup in December. Their seniors and best underclassmen then enter MLS's "
            "SuperDraft pool."]


def recruit(conn: Connection, world: World, meta: CareerMeta, season_id: int,
            day: date) -> int:
    """Every program's freshman class: enough to get its roster back to the target, the
    positions it lacks first. Returns how many arrived."""
    rules = world.defs.college.rules
    shape = rules.roster.shape[:rules.recruiting.roster_target]
    wanted = Counter(shape)
    have: dict[int, Counter[str]] = defaultdict(Counter)
    for r in conn.execute(text(f"""
            SELECT cp.club_id, (SELECT position FROM player_position pp
                                WHERE pp.player_id = cp.player_id
                                ORDER BY familiarity DESC, position LIMIT 1) AS position
            FROM college_player cp WHERE cp.player_id IN ({IN_COLLEGE_SQL})
            AND cp.status = '{ENROLLED}'""")):
        have[int(r.club_id)][str(r.position)] += 1
    teams = conn.execute(select(college_team.c.club_id, college_team.c.level, club.c.reputation)
                         .join(club, club.c.id == college_team.c.club_id)
                         .order_by(college_team.c.club_id)).all()
    maker = _Maker(conn, world, meta, day)
    low, high = rules.recruiting.recruits
    for t in teams:
        rng = derive_rng(meta.seed, "college-recruit", season_id, int(t.club_id))
        count = sum(have[int(t.club_id)].values())
        size = int(min(high, max(low, rules.recruiting.roster_target - count)))
        short = Counter({p: n - have[int(t.club_id)][p] for p, n in wanted.items()
                         if n > have[int(t.club_id)][p]})
        positions = []
        for p in shape:  # by depth: a missing starter's position first
            if short[p] > 0:
                positions.append(p)
                short[p] -= 1
        while len(positions) < size:
            positions.append(shape[int(rng.integers(len(shape)))])
        for position in positions[:size]:
            maker.make(int(t.club_id), int(t.reputation), position, 1,
                       _age(rules, rules.recruiting.age, rules.recruiting.age_sd, rng),
                       _player_overall(rules, float(t.level), 1, rng), season_id)
    maker.rows.write(conn, with_state=True)
    if maker.rows.count:
        bump_players_epoch(conn)
    return maker.rows.count
