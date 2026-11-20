"""The World Cup finals (W8 I4, data/config/international/world_cup.yaml): 48 teams, FIFA's 2026
format, the 2030 edition.

On the draw day (once qualifying is over) the qualified teams are drawn into 12 groups of 4: the
hosts and the best by Elo in pot 1, no group with two teams of one confederation (UEFA's at most
two). The day before the first match every team calls up its squad, and its players are away
from their clubs until the final. Hosts play their group matches at home, everything else is at
neutral venues. The top two of each group and the 8 best third-placed teams play a round of 32,
seeded by their group results with no group rematch, then single matches (extra time and
penalties) to the final, with a match for third place. Elo moves at the finals' weight
(``WCF:`` stages). Competition ``WC`` (type ``international``); groups' stage ``WCF:G`` with the
group's letter as ``tie``; knockouts ``WCF:R32`` ... ``WCF:F`` and ``WCF:3P``.
"""

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
from sqlalchemy import Connection, text

from footsim.core.rng import derive_rng
from footsim.match.report import Decider
from footsim.persistence.schema import fixture
from footsim.world.context import World
from footsim.world.international.common import AWAY_KEY
from footsim.world.meta import CareerMeta

KEY = "WC"
GROUPS = "WCF:G"
ROUNDS = ("R32", "R16", "QF", "SF", "F")
ROUND_NAMES = {"R32": "Round of 32", "R16": "Round of 16", "QF": "Quarter-finals",
               "SF": "Semi-finals", "3P": "Match for third place", "F": "Final"}
LETTERS = "ABCDEFGHIJKL"
STATE_KEY = "wc_finals"  # game_meta: the draw's groups, the squads' call-up, the champion


def _get(conn: Connection) -> Any:
    value = conn.execute(text("SELECT value FROM game_meta WHERE key = :k"),
                         {"k": STATE_KEY}).scalar()
    return json.loads(value) if value is not None else None


def _set(conn: Connection, value: Any, key: str = STATE_KEY) -> None:
    conn.execute(text("INSERT INTO game_meta (key, value) VALUES (:k, :v) "
                      "ON CONFLICT(key) DO UPDATE SET value = excluded.value"),
                 {"k": key, "v": json.dumps(value)})


def is_finals(stage: str) -> bool:
    return stage.startswith("WCF:")


def decider(fx: Any) -> Decider | None:
    return None if fx.stage == GROUPS else Decider(extra_time=True, penalties=True)


@dataclass
class _Team:
    club_id: int
    code: str
    confederation: str
    elo: float
    host: bool


def _teams(conn: Connection, world: World) -> list[_Team]:
    from footsim.world.international.qualifiers import qualified_teams

    through = qualified_teams(conn)
    hosts = set(world.defs.international.qualifiers.hosts)
    return [_Team(int(r.club_id), str(r.code), str(r.confederation), float(r.elo),
                  str(r.code) in hosts)
            for r in conn.execute(text("SELECT club_id, code, confederation, elo "
                                       "FROM national_team ORDER BY code"))
            if str(r.code) in through]


def draw_groups(teams: list[_Team], rng: np.random.Generator) -> list[list[_Team]]:
    """12 groups of 4: pot 1 the hosts and the best by Elo, then pots by Elo; no group with two
    teams of one confederation, UEFA's at most two; pots redrawn until they fit."""
    hosts = [t for t in teams if t.host]
    rest = sorted((t for t in teams if not t.host), key=lambda t: (-t.elo, t.code))
    ordered = hosts + rest
    pots = [ordered[k * 12:(k + 1) * 12] for k in range(4)]

    def allowed(group: list[_Team], t: _Team) -> bool:
        same = sum(1 for g in group if g.confederation == t.confederation)
        return same < (2 if t.confederation == "UEFA" else 1)

    for _ in range(2000):
        groups: list[list[_Team]] = [[] for _ in range(12)]
        ok = True
        for k, pot in enumerate(pots):
            order = list(pot)
            if k > 0 or not hosts:
                rng.shuffle(order)
            free = list(range(12))
            for t in order:
                options = [g for g in free if allowed(groups[g], t)]
                if not options:
                    ok = False
                    break
                # The hosts head groups A, B and C in turn (as FIFA placed them).
                g = options[0] if (k == 0 and t.host) else options[int(rng.integers(len(options)))]
                groups[g].append(t)
                free.remove(g)
            if not ok:
                break
        if ok:
            return groups
    raise RuntimeError("no World Cup draw satisfies the confederation rules")


def _day(value: str) -> date:
    return date.fromisoformat(value)


def _insert(conn: Connection, meta: CareerMeta, comp: int, stage: str,
            rows: list[tuple[date, int, int, str, int, bool]]) -> None:
    if rows:
        conn.execute(fixture.insert(), [
            {"season_id": meta.season_id, "competition_id": comp, "stage": stage, "round": rnd,
             "tie": tie, "leg": None, "date": day.isoformat(), "home_club_id": home,
             "away_club_id": away, "neutral": int(neutral), "status": "scheduled"}
            for day, home, away, tie, rnd, neutral in rows])


def _competition(conn: Connection, world: World) -> int:
    from footsim.world.international.windows import competition_id

    year = world.defs.international.world_cup.year
    return competition_id(conn, KEY, f"FIFA World Cup {year}", "World Cup")


def _draw(conn: Connection, world: World, meta: CareerMeta) -> list[str]:
    spec = world.defs.international.world_cup
    teams = _teams(conn, world)
    if len(teams) != 48:
        return []  # qualifying isn't over: drawn when it is
    rng = derive_rng(meta.seed, "wc-draw", spec.year)
    groups = draw_groups(teams, rng)
    comp = _competition(conn, world)
    days = [_day(d) for d in spec.groups]
    rows = []
    for g, members in enumerate(groups):
        a, b, c, d = members
        for r, pairs in enumerate((((a, b), (c, d)), ((a, c), (d, b)), ((d, a), (b, c)))):
            for home, away in pairs:
                if away.host and not home.host:
                    home, away = away, home
                rows.append((days[r], home.club_id, away.club_id, LETTERS[g], r + 1,
                             not home.host))
    _insert(conn, meta, comp, GROUPS, rows)
    _set(conn, {"groups": {LETTERS[g]: [t.club_id for t in m] for g, m in enumerate(groups)},
                "called": False, "champion": None})
    return [f"The {spec.year} World Cup draw is made: 48 teams in 12 groups, from "
            f"{days[0].strftime('%-d %B')}."]


@dataclass
class _Row:
    club_id: int
    group: str
    points: int = 0
    gd: int = 0
    gf: int = 0


def group_tables(conn: Connection, elo: dict[int, float]) -> dict[str, list[_Row]]:
    rows: dict[str, dict[int, _Row]] = {}
    for f in conn.execute(text("SELECT * FROM fixture WHERE stage = :s ORDER BY id"),
                          {"s": GROUPS}):
        group = rows.setdefault(f.tie, {})
        for c in (f.home_club_id, f.away_club_id):
            group.setdefault(c, _Row(c, f.tie))
        if f.status != "played":
            continue
        for c, us, them in ((f.home_club_id, f.home_goals, f.away_goals),
                            (f.away_club_id, f.away_goals, f.home_goals)):
            r = group[c]
            r.gf += us
            r.gd += us - them
            r.points += 3 if us > them else 1 if us == them else 0
    return {g: sorted(m.values(), key=lambda r: (-r.points, -r.gd, -r.gf,
                                                  -elo.get(r.club_id, 0.0), r.club_id))
            for g, m in sorted(rows.items())}


def _record(r: _Row, elo: dict[int, float]) -> tuple[float, ...]:
    return (-r.points, -r.gd, -r.gf, -elo.get(r.club_id, 0.0), r.club_id)


def round_of_32(tables: dict[str, list[_Row]], elo: dict[int, float]) -> list[tuple[int, int]]:
    """The 32 seeded by group results (winners, runners-up, the 8 best thirds), paired 1 v 32,
    2 v 31...; a pair from one group swaps its lower seed with the next pair's."""
    winners = sorted((t[0] for t in tables.values()), key=lambda r: _record(r, elo))
    seconds = sorted((t[1] for t in tables.values()), key=lambda r: _record(r, elo))
    thirds = sorted((t[2] for t in tables.values()), key=lambda r: _record(r, elo))[:8]
    seeds = winners + seconds + thirds
    top, bottom = seeds[:16], list(reversed(seeds[16:]))
    for k in range(16):
        if top[k].group == bottom[k].group:
            j = next((j for j in range(16) if j != k and bottom[j].group != top[k].group
                      and bottom[k].group != top[j].group), None)
            if j is not None:
                bottom[k], bottom[j] = bottom[j], bottom[k]
    # Bracket order: the best seed meets the 16th-best's path only in the final.
    order = [0, 15, 7, 8, 3, 12, 4, 11, 1, 14, 6, 9, 2, 13, 5, 10]
    return [(top[k].club_id, bottom[k].club_id) for k in order]


def _winner(f: Any) -> int | None:
    if f.status != "played":
        return None
    if f.home_goals != f.away_goals:
        return int(f.home_club_id if f.home_goals > f.away_goals else f.away_club_id)
    if f.home_pens is None:
        return None
    return int(f.home_club_id if f.home_pens > f.away_pens else f.away_club_id)


def _loser(f: Any) -> int | None:
    w = _winner(f)
    if w is None:
        return None
    return int(f.away_club_id if w == f.home_club_id else f.home_club_id)


def _stage(conn: Connection, rnd: str) -> list[Any]:
    return list(conn.execute(text("SELECT * FROM fixture WHERE stage = :s "
                                  "ORDER BY CAST(tie AS INTEGER)"), {"s": f"WCF:{rnd}"}).all())


def _progress(conn: Connection, world: World, meta: CareerMeta) -> list[str]:
    spec = world.defs.international.world_cup
    comp = _competition(conn, world)
    elo = {int(r.club_id): float(r.elo) for r in conn.execute(text(
        "SELECT club_id, elo FROM national_team"))}
    news: list[str] = []
    groups = list(conn.execute(text("SELECT status FROM fixture WHERE stage = :s"),
                               {"s": GROUPS}).all())
    if groups and all(f.status == "played" for f in groups) and not _stage(conn, "R32"):
        pairs = round_of_32(group_tables(conn, elo), elo)
        _insert(conn, meta, comp, "WCF:R32", [(_day(spec.round_of_32), h, a, str(n + 1), 1, True)
                                               for n, (h, a) in enumerate(pairs)])
    days = {"R16": spec.round_of_16, "QF": spec.quarter_finals, "SF": spec.semi_finals,
            "F": spec.final}
    for before, after in zip(ROUNDS, ROUNDS[1:], strict=False):
        done = _stage(conn, before)
        if not done or _stage(conn, after) or any(_winner(f) is None for f in done):
            continue
        winners = [int(w) for f in done if (w := _winner(f)) is not None]
        pairs = [(winners[k], winners[k + 1]) for k in range(0, len(winners), 2)]
        _insert(conn, meta, comp, f"WCF:{after}", [(_day(days[after]), h, a, str(n + 1), 1, True)
                                                    for n, (h, a) in enumerate(pairs)])
        if after == "F":
            losers = [int(x) for f in done if (x := _loser(f)) is not None]
            _insert(conn, meta, comp, "WCF:3P", [(_day(spec.third_place), losers[0], losers[1],
                                                  "1", 1, True)])
    final = _stage(conn, "F")
    state = _get(conn) or {}
    if final and state.get("champion") is None and _winner(final[0]) is not None:
        champion = _winner(final[0])
        state["champion"] = champion
        _set(conn, state)
        name: str = conn.execute(text("SELECT name FROM club WHERE id = :c"),
                            {"c": champion}).scalar_one()
        news.append(f"{name} win the {spec.year} World Cup.")
    return news


def finals_day(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """The draw on its day (or the first day after it with qualifying over), the call-ups the
    day before the first match, then the knockouts as rounds are decided. Returns news."""
    spec = world.defs.international.world_cup
    state = _get(conn)
    if state is None:
        if day >= _day(spec.draw):
            return _draw(conn, world, meta)
        return []
    news: list[str] = []
    first = _day(spec.groups[0])
    if not state.get("called") and day >= first - timedelta(days=1):
        from footsim.world.international.teams import pick_squads

        clubs = [int(c) for members in state["groups"].values() for c in members]
        codes = {str(r.code) for r in conn.execute(text(
            "SELECT code FROM national_team WHERE club_id IN (SELECT value FROM json_each(:c))"),
            {"c": json.dumps(clubs)})}
        # Only the finalists' players are away: earlier windows' squads of the others go.
        conn.execute(text("DELETE FROM national_squad WHERE club_id NOT IN "
                          "(SELECT value FROM json_each(:c))"), {"c": json.dumps(clubs)})
        pick_squads(conn, world, meta, day, codes)
        _set(conn, {"start": first.isoformat(), "end": spec.final}, AWAY_KEY)
        state["called"] = True
        _set(conn, state)
    if day >= first:
        news += _progress(conn, world, meta)
    return news
