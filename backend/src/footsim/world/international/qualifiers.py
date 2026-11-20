"""The World Cup qualifiers (W8 I3), realistic-lite, from data/config/international/
qualifiers_2030.yaml.

Each stage is drawn the day before its first window: a group stage from Elo pots, its rounds on
the stage's matchdays one after another; play-off paths seeded by Elo, their semi-finals first and
each final once its semi-finals are decided. The teams a stage's ``qualified_ranks`` or
``qualified_winners`` name are through to the finals (``game_meta`` ``wc_qualified``, with the
hosts from the start). Fixtures: competition ``WCQ``, stage ``WCQ:<stage key>``; a group's
fixtures carry its letter as ``tie``, a path's ``<path>-SF<n>`` or ``<path>-F``.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Connection, text

from footsim.competitions.calendars import shifted_calendar
from footsim.competitions.fixtures import round_robin
from footsim.core.rng import derive_rng
from footsim.defs.calendar import DateRange
from footsim.defs.international import EntrantSourceDef, QualifierStageDef
from footsim.match.report import Decider
from footsim.persistence.schema import fixture
from footsim.world.context import World
from footsim.world.meta import CareerMeta

STAGE = "WCQ:"  # fixture.stage = STAGE + the stage's key
KEY = "WCQ"  # the qualifiers' competition
QUALIFIED_KEY = "wc_qualified"  # game_meta: {code: how it qualified}
DONE_KEY = "wcq_done"  # game_meta: the stages whose outcomes are recorded
LETTERS = "ABCDEFGHIJKLMNOP"


def is_qualifier(stage: str) -> bool:
    return stage.startswith(STAGE)


def _meta_get(conn: Connection, key: str) -> Any:
    value = conn.execute(text("SELECT value FROM game_meta WHERE key = :k"), {"k": key}).scalar()
    return json.loads(value) if value is not None else None


def _meta_set(conn: Connection, key: str, value: Any) -> None:
    conn.execute(text("INSERT INTO game_meta (key, value) VALUES (:k, :v) "
                      "ON CONFLICT(key) DO UPDATE SET value = excluded.value"),
                 {"k": key, "v": json.dumps(value)})


_WINDOWS: dict[str, dict[str, DateRange]] = {}  # by base calendar: they never change


def career_windows(world: World, meta: CareerMeta) -> dict[str, DateRange]:
    """FIFA's windows over the career's first eight seasons, by "YYYY-MM" of their start."""
    found = _WINDOWS.get(meta.base_calendar)
    if found is None:
        base = world.defs.calendars[meta.base_calendar]
        found = {w.start.strftime("%Y-%m"): w for k in range(8)
                 for w in shifted_calendar(base, k).international_windows}
        _WINDOWS[meta.base_calendar] = found
    return found


def stage_days(world: World, meta: CareerMeta, stage: QualifierStageDef) -> list[date]:
    from footsim.world.international.windows import matchdays

    windows = career_windows(world, meta)
    return [d for ym in stage.windows for d in matchdays(world, windows[ym])]


def draw_day(world: World, meta: CareerMeta, stage: QualifierStageDef) -> date:
    first = career_windows(world, meta)[stage.windows[0]]
    return first.start - timedelta(days=world.defs.international.qualifiers.draw_days_before)


@dataclass
class _Teams:
    elo: dict[int, float]
    code: dict[int, str]
    confederation: dict[int, str]
    name: dict[int, str]

    @classmethod
    def load(cls, conn: Connection) -> "_Teams":
        rows = conn.execute(text("SELECT t.club_id, t.code, t.confederation, t.elo, c.name "
                                 "FROM national_team t JOIN club c ON c.id = t.club_id")).all()
        return cls({int(r.club_id): float(r.elo) for r in rows},
                   {int(r.club_id): str(r.code) for r in rows},
                   {int(r.club_id): str(r.confederation) for r in rows},
                   {int(r.club_id): str(r.name) for r in rows})


def _fixtures(conn: Connection, key: str) -> list[Any]:
    return list(conn.execute(text("SELECT * FROM fixture WHERE stage = :s ORDER BY id"),
                             {"s": STAGE + key}).all())


# --- tables and ties ---------------------------------------------------------------------


@dataclass
class Row:
    club_id: int
    played: int = 0
    points: int = 0
    gd: int = 0
    gf: int = 0


def group_tables(conn: Connection, key: str, teams: _Teams) -> dict[str, list[Row]]:
    """Each group's table, best first: points, goal difference, goals, then Elo."""
    rows: dict[str, dict[int, Row]] = {}
    for f in _fixtures(conn, key):
        group = rows.setdefault(f.tie, {})
        for c in (f.home_club_id, f.away_club_id):
            group.setdefault(c, Row(c))
        if f.status != "played":
            continue
        for c, us, them in ((f.home_club_id, f.home_goals, f.away_goals),
                            (f.away_club_id, f.away_goals, f.home_goals)):
            r = group[c]
            r.played += 1
            r.gf += us
            r.gd += us - them
            r.points += 3 if us > them else 1 if us == them else 0
    return {g: sorted(members.values(), key=lambda r: (-r.points, -r.gd, -r.gf,
                                                        -teams.elo[r.club_id], r.club_id))
            for g, members in sorted(rows.items())}


def _tie_result(legs: list[Any]) -> tuple[int, int] | None:
    """A path tie's (winner, loser), once all its legs are played; None before."""
    if not legs or any(f.status != "played" for f in legs):
        return None
    last = legs[-1]
    a, b = last.home_club_id, last.away_club_id
    goals = {a: 0, b: 0}
    for f in legs:
        goals[f.home_club_id] += f.home_goals
        goals[f.away_club_id] += f.away_goals
    if goals[a] == goals[b]:
        if last.home_pens is None or last.home_pens == last.away_pens:
            return None
        return (a, b) if last.home_pens > last.away_pens else (b, a)
    return (a, b) if goals[a] > goals[b] else (b, a)


def path_ties(conn: Connection, key: str) -> dict[str, list[Any]]:
    ties: dict[str, list[Any]] = {}
    for f in _fixtures(conn, key):
        ties.setdefault(f.tie, []).append(f)
    return ties


def decider(conn: Connection, world: World, fx: Any) -> Decider | None:
    """Knockout rules for a qualifier: None in a group; a path's single match or second leg
    goes to extra time and penalties (with the first leg's goals)."""
    stage = _stage(world, fx.stage[len(STAGE):])
    if stage is None or stage.format == "groups":
        return None
    if stage.legs == 1:
        return Decider(extra_time=True, penalties=True)
    if fx.leg != 2:
        return None
    first = conn.execute(text("SELECT * FROM fixture WHERE stage = :s AND tie = :t AND leg = 1"),
                         {"s": fx.stage, "t": fx.tie}).one()
    prior = ((first.home_goals, first.away_goals) if first.home_club_id == fx.home_club_id
             else (first.away_goals, first.home_goals))
    return Decider(extra_time=True, penalties=True, first_leg=prior)


def _stage(world: World, key: str) -> QualifierStageDef | None:
    return next((s for s in world.defs.international.qualifiers.stages if s.key == key), None)


# --- entrants ----------------------------------------------------------------------------


def _record_key(r: Row, teams: _Teams) -> tuple[float, float, float, float]:
    """Comparing teams across groups of different sizes: per game."""
    n = max(r.played, 1)
    return (-r.points / n, -r.gd / n, -r.gf / n, -teams.elo[r.club_id])


def _from_source(conn: Connection, world: World, source: EntrantSourceDef, teams: _Teams
                 ) -> list[int]:
    stage = _stage(world, source.stage)
    assert stage is not None
    if source.winners or source.losers:
        ties = path_ties(conn, source.stage)
        finals = [legs for tie, legs in ties.items() if tie.endswith("-F")]
        picked = []
        for legs in finals:
            result = _tie_result(legs)
            if result is not None:
                picked.append(result[0] if source.winners else result[1])
        return sorted(picked, key=lambda c: -teams.elo[c])
    tables = group_tables(conn, source.stage, teams)
    if source.ranks is not None:
        low, high = source.ranks
        found = [r for table in tables.values() for r in table[low - 1:high]]
        found.sort(key=lambda r: (_rank_of(tables, r.club_id), *_record_key(r, teams)))
        return [r.club_id for r in found]
    assert source.best is not None and source.rank is not None
    at = [table[source.rank - 1] for table in tables.values() if len(table) >= source.rank]
    at.sort(key=lambda r: _record_key(r, teams))
    return [r.club_id for r in at[:source.best]]


def _rank_of(tables: dict[str, list[Row]], club_id: int) -> int:
    return next(k for table in tables.values() for k, r in enumerate(table) if r.club_id == club_id)


def entrants(conn: Connection, world: World, stage: QualifierStageDef, teams: _Teams
             ) -> list[int]:
    spec = stage.entrants
    if spec.confederation is not None:
        hosts = set(world.defs.international.qualifiers.hosts)
        pool = [c for c, conf in teams.confederation.items()
                if conf == spec.confederation and teams.code[c] not in hosts]
        pool.sort(key=lambda c: (-teams.elo[c], c))
        return pool[:spec.top] if spec.top else pool
    found: list[int] = []
    for source in spec.from_:
        found += [c for c in _from_source(conn, world, source, teams) if c not in found]
    return found


# --- the draw and the paths --------------------------------------------------------------


def _insert(conn: Connection, meta: CareerMeta, comp: int, stage: QualifierStageDef,
            rows: Sequence[tuple[date, int, int, str, int, int | None]]) -> None:
    """Fixtures as (date, home, away, tie, round, leg)."""
    if rows:
        conn.execute(fixture.insert(), [
            {"season_id": meta.season_id, "competition_id": comp, "stage": STAGE + stage.key,
             "round": rnd, "tie": tie, "leg": leg, "date": day.isoformat(),
             "home_club_id": home, "away_club_id": away, "neutral": int(stage.neutral),
             "status": "scheduled"} for day, home, away, tie, rnd, leg in rows])


def _draw_groups(conn: Connection, world: World, meta: CareerMeta, comp: int,
                 stage: QualifierStageDef, teams: _Teams) -> None:
    clubs = entrants(conn, world, stage, teams)
    rng = derive_rng(meta.seed, "wcq-draw", stage.key)
    groups: list[list[int]] = [[] for _ in range(stage.groups)]
    for k in range(0, len(clubs), stage.groups):
        pot = list(clubs[k:k + stage.groups])
        rng.shuffle(pot)
        for g, club_id in enumerate(pot):
            groups[g].append(club_id)
    days = stage_days(world, meta, stage)
    rows = []
    for g, members in enumerate(groups):
        for r, pairs in enumerate(round_robin(members, stage.legs, rng)):
            if r >= len(days):
                raise ValueError(f"{stage.key}: more rounds than matchdays")
            rows += [(days[r], home, away, LETTERS[g], r + 1, None) for home, away in pairs]
    _insert(conn, meta, comp, stage, rows)


def _paths(clubs: list[int], count: int) -> list[list[int]]:
    """Seeds into ``count`` paths, snaking (1, 2, 2, 1, 1, 2...), each path best first."""
    paths: list[list[int]] = [[] for _ in range(count)]
    for k, club_id in enumerate(clubs):
        lap, at = divmod(k, count)
        paths[at if lap % 2 == 0 else count - 1 - at].append(club_id)
    return paths


def _tie_rows(days: list[date], legs: int, first_day: int, better: int, worse: int, tie: str,
              rnd: int) -> list[tuple[date, int, int, str, int, int | None]]:
    if legs == 1:
        return [(days[first_day], better, worse, tie, rnd, None)]
    return [(days[first_day], worse, better, tie, rnd, 1),
            (days[first_day + 1], better, worse, tie, rnd, 2)]


def _draw_paths(conn: Connection, world: World, meta: CareerMeta, comp: int,
                stage: QualifierStageDef, teams: _Teams) -> None:
    clubs = sorted(entrants(conn, world, stage, teams), key=lambda c: (-teams.elo[c], c))
    days = stage_days(world, meta, stage)
    rows = []
    for p, seeds in enumerate(_paths(clubs, stage.paths)):
        letter = LETTERS[p]
        if len(seeds) == 4:
            rows += _tie_rows(days, stage.legs, 0, seeds[0], seeds[3], f"{letter}-SF1", 1)
            rows += _tie_rows(days, stage.legs, 0, seeds[1], seeds[2], f"{letter}-SF2", 1)
        elif len(seeds) == 3:
            rows += _tie_rows(days, stage.legs, 0, seeds[1], seeds[2], f"{letter}-SF1", 1)
        elif len(seeds) == 2:
            rows += _tie_rows(days, stage.legs, 0, seeds[0], seeds[1], f"{letter}-F", 1)
        else:
            raise ValueError(f"{stage.key}: a path of {len(seeds)}")
    _insert(conn, meta, comp, stage, rows)
    _meta_set(conn, f"wcq_seeds:{stage.key}",
              {LETTERS[p]: seeds for p, seeds in enumerate(_paths(clubs, stage.paths))})


def _progress_paths(conn: Connection, world: World, meta: CareerMeta, comp: int,
                    stage: QualifierStageDef, teams: _Teams) -> None:
    """Each path's final, once its semi-finals are decided."""
    ties = path_ties(conn, stage.key)
    seeds = _meta_get(conn, f"wcq_seeds:{stage.key}") or {}
    days = stage_days(world, meta, stage)
    later = 1 if stage.legs == 1 else 2
    rows = []
    for letter, path in seeds.items():
        if f"{letter}-F" in ties:
            continue
        semis = [ties.get(f"{letter}-SF{n}") for n in (1, 2) if f"{letter}-SF{n}" in ties]
        results = [_tie_result(legs) for legs in semis if legs]
        if not results or any(r is None for r in results):
            continue
        winners = [r[0] for r in results if r is not None]
        finalists = winners if len(path) == 4 else [path[0], winners[0]]
        better, worse = sorted(finalists, key=lambda c: (-teams.elo[c], c))
        rows += _tie_rows(days, stage.legs, later, better, worse, f"{letter}-F", 2)
    _insert(conn, meta, comp, stage, rows)


# --- the day -----------------------------------------------------------------------------


def qualifiers_day(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """Draw the stages due tomorrow's window, add path finals, and record who has qualified
    once a stage is over. Returns news."""
    from footsim.world.international.windows import competition_id

    spec = world.defs.international.qualifiers
    news: list[str] = []
    qualified: dict[str, str] = _meta_get(conn, QUALIFIED_KEY) or {}
    if not qualified:
        qualified = {code: "Hosts" for code in spec.hosts}
        _meta_set(conn, QUALIFIED_KEY, qualified)
    done: list[str] = _meta_get(conn, DONE_KEY) or []
    teams: _Teams | None = None
    for stage in spec.stages:
        if stage.key in done:
            continue
        drawn = conn.execute(text("SELECT 1 FROM fixture WHERE stage = :s LIMIT 1"),
                             {"s": STAGE + stage.key}).first() is not None
        if not drawn and draw_day(world, meta, stage) != day:
            continue
        teams = teams or _Teams.load(conn)
        comp = competition_id(conn, KEY, f"World Cup {spec.cycle} qualifiers", "WC qualifiers")
        if not drawn:
            if stage.format == "groups":
                _draw_groups(conn, world, meta, comp, stage, teams)
            else:
                _draw_paths(conn, world, meta, comp, stage, teams)
            continue
        if stage.format == "paths":
            _progress_paths(conn, world, meta, comp, stage, teams)
        if _complete(conn, stage):
            news += _record(conn, world, stage, teams, qualified, spec.cycle)
            done.append(stage.key)
            _meta_set(conn, DONE_KEY, done)
            _meta_set(conn, QUALIFIED_KEY, qualified)
    return news


def _complete(conn: Connection, stage: QualifierStageDef) -> bool:
    """Every match played; for paths, every path's final decided."""
    rows = _fixtures(conn, stage.key)
    if not rows or any(f.status != "played" for f in rows):
        return False
    if stage.format == "groups":
        return True
    ties = path_ties(conn, stage.key)
    letters = (_meta_get(conn, f"wcq_seeds:{stage.key}") or {}).keys()
    return all(_tie_result(ties.get(f"{letter}-F", [])) is not None for letter in letters)


def _record(conn: Connection, world: World, stage: QualifierStageDef, teams: _Teams,
            qualified: dict[str, str], cycle: int) -> list[str]:
    through: list[int] = []
    if stage.format == "groups" and stage.qualified_ranks is not None:
        low, high = stage.qualified_ranks
        through = [r.club_id for table in group_tables(conn, stage.key, teams).values()
                   for r in table[low - 1:high]]
    elif stage.format == "paths" and stage.qualified_winners:
        through = [result[0] for tie, legs in path_ties(conn, stage.key).items()
                   if tie.endswith("-F") and (result := _tie_result(legs)) is not None]
    for club_id in through:
        qualified[teams.code[club_id]] = stage.name
    if not through:
        return []
    names = ", ".join(sorted(teams.name[c] for c in through))
    return [f"World Cup {cycle}: {names} qualify ({stage.name})."]


def qualified_teams(conn: Connection) -> dict[str, str]:
    """The teams through to the finals so far, by code, with how."""
    return dict(_meta_get(conn, QUALIFIED_KEY) or {})

