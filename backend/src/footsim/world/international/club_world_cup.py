"""The FIFA Club World Cup (W10, data/config/international/club_world_cup.yaml): 32 clubs every
four years from 2029, in FIFA's 2025 format.

On the draw day (December, the year before) the entrants are chosen: UEFA's 12 are the Champions
League winners of the career's editions so far and then the best by UEFA's club coefficient;
every other confederation's are its clubs in the game's leagues and its guest clubs
(world/international/guests.py), ranked by strength (the best 16 players' average overall, plus
a bonus for each league title since the career began); and the host country's best club not
already in. At most ``per_country`` clubs of a country, unless more are Champions League winners.
They are drawn into 8 groups of 4 from pots by strength, no group with two clubs of one
confederation (UEFA's, at most two). The groups play at neutral venues in mid-June, the top two
go through to the round of 16 (A1 v B2, B1 v A2, ...), and single-match knockouts end with the
final in mid-July. Prize money is paid as FIFA's 2025 was. The fixtures don't hold up the
season's rollover. Competition ``CWC`` (type ``club_world_cup``); group fixtures' stage
``CWC:G`` with the group's letter as ``tie``; knockouts ``CWC:R16``, ``CWC:QF``, ``CWC:SF``,
``CWC:F`` with ``tie`` the match's number.
"""

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
from sqlalchemy import Connection, text

from footsim.core.rng import derive_rng
from footsim.domain.attributes import ATTRIBUTES
from footsim.match.report import Decider
from footsim.persistence.schema import competition, fixture
from footsim.world.context import World
from footsim.world.europe.common import KNOCKOUT
from footsim.world.finance import Entry, post
from footsim.world.lifecycle import _own_overalls
from footsim.world.meta import CareerMeta

TYPE = "club_world_cup"
KEY = "CWC"
GROUPS = "CWC:G"
ROUNDS = ("R16", "QF", "SF", "F")
ROUND_NAMES = {"R16": "Round of 16", "QF": "Quarter-finals", "SF": "Semi-finals", "F": "Final"}
LETTERS = "ABCDEFGH"


def is_cwc(stage: str) -> bool:
    return stage.startswith("CWC:")


def _meta_key(year: int) -> str:
    return f"cwc:{year}"


def _get(conn: Connection, key: str) -> Any:
    value = conn.execute(text("SELECT value FROM game_meta WHERE key = :k"), {"k": key}).scalar()
    return json.loads(value) if value is not None else None


def _set(conn: Connection, key: str, value: Any) -> None:
    conn.execute(text("INSERT INTO game_meta (key, value) VALUES (:k, :v) "
                      "ON CONFLICT(key) DO UPDATE SET value = excluded.value"),
                 {"k": key, "v": json.dumps(value)})


def edition_on(world: World, day: date) -> int | None:
    """The edition whose draw or tournament falls in the year around ``day``, if any."""
    spec = world.defs.international.club_world_cup
    for year in (day.year, day.year + 1):
        if year >= spec.first_year and (year - spec.first_year) % spec.every_years == 0:
            return year
    return None


def _day(year: int, month_day: str) -> date:
    month, day = (int(x) for x in month_day.split("-"))
    return date(year, month, day)


def draw_date(world: World, year: int) -> date:
    return _day(year - 1, world.defs.international.club_world_cup.draw)


def competition_id(conn: Connection, year: int) -> int:
    found = conn.execute(text("SELECT id FROM competition WHERE key = :k"), {"k": KEY}).scalar()
    if found is not None:
        return int(found)
    return int(conn.execute(competition.insert().values(
        key=KEY, name="FIFA Club World Cup", short_name="Club World Cup", nation_id=None,
        type=TYPE, tier=None, sim_level="playable")).lastrowid)


# --- the entrants ------------------------------------------------------------------------


@dataclass
class Entrant:
    club_id: int
    confederation: str
    country: str
    how: str
    strength: float


def _levels(conn: Connection, world: World, club_ids: list[int]) -> dict[int, float]:
    """Each club's level: the average overall (in their main positions) of its best 16 players
    (a guest's own players, a club's contracted ones)."""
    if not club_ids:
        return {}
    marks = ", ".join(str(int(c)) for c in club_ids)
    rows = conn.execute(text(f"""
        SELECT k.club_id, {", ".join("a." + a for a in ATTRIBUTES)},
            (SELECT position FROM player_position pp WHERE pp.player_id = k.person_id
             ORDER BY familiarity DESC, position LIMIT 1) AS position
        FROM (SELECT club_id, person_id FROM playing
              UNION ALL SELECT club_id, player_id FROM guest_player) k
        JOIN player_attr a ON a.player_id = k.person_id
        WHERE k.club_id IN ({marks})""")).all()
    if not rows:
        return {}
    attrs = np.array([[getattr(r, a) for a in ATTRIBUTES] for r in rows], dtype=float)
    overalls = _own_overalls(world, attrs, [str(r.position or "CM") for r in rows])
    by_club: dict[int, list[float]] = {}
    for r, value in zip(rows, overalls, strict=True):
        by_club.setdefault(int(r.club_id), []).append(float(value))
    return {c: float(np.mean(sorted(v, reverse=True)[:16])) for c, v in by_club.items()}


def _countries(conn: Connection, world: World) -> dict[int, str]:
    """Each club's country as a FIFA code: by the national teams' nationalities (the game's
    nation rows often have no code), else the nation's own code."""
    from footsim.world.international.common import nation_ids

    by_nation = {nid: code for code, ids in nation_ids(conn, world).items() for nid in ids}
    found = {}
    for r in conn.execute(text("SELECT c.id, c.nation_id, n.code FROM club c "
                               "LEFT JOIN nation n ON n.id = c.nation_id")):
        code = by_nation.get(r.nation_id) or r.code
        if code:
            found[int(r.id)] = str(code)
    return found


def _confederation_of(world: World, country: str) -> str | None:
    team = world.defs.international.teams.get(country)
    return team.confederation if team is not None else None


def _ucl_winners(conn: Connection, world: World, before: date) -> list[int]:
    """The Champions League's winners in the career, finals played before ``before``."""
    comp = world.defs.continental.get("UCL")
    if comp is None:
        return []
    final = KNOCKOUT + len(comp.knockout) - 1
    rows = conn.execute(text(
        "SELECT t.season_id, t.winner_club_id FROM cup_tie t JOIN competition c "
        "ON c.id = t.competition_id WHERE c.key = 'UCL' AND t.round = :r "
        "AND t.winner_club_id IS NOT NULL ORDER BY t.season_id"), {"r": final}).all()
    winners = []
    for r in rows:
        played = conn.execute(text(
            "SELECT MAX(date) FROM fixture WHERE season_id = :s AND stage = 'UCL'"),
            {"s": r.season_id}).scalar()
        if played is not None and date.fromisoformat(played) < before:
            winners.append(int(r.winner_club_id))
    return winners


def choose_entrants(conn: Connection, world: World, meta: CareerMeta, year: int
                    ) -> list[Entrant]:
    """The 32 clubs for the ``year`` edition, chosen on its draw day."""
    from footsim.world.europe.coefficients import coefficients

    spec = world.defs.international.club_world_cup
    day = draw_date(world, year)
    country = _countries(conn, world)
    in_league = {int(r.club_id): str(r.key) for r in conn.execute(text(
        "SELECT m.club_id, c.key FROM club_league_membership m JOIN competition c "
        "ON c.id = m.competition_id WHERE m.season_id = :s AND c.type = 'league'"),
        {"s": meta.season_id})}
    guests = {int(r.club_id): str(r.confederation) for r in conn.execute(text(
        "SELECT club_id, confederation FROM guest_club"))}
    titles: dict[int, int] = {}
    for r in conn.execute(text("SELECT club_id, COUNT(*) AS n FROM league_title "
                               "WHERE kind = 'champion' GROUP BY club_id")):
        titles[int(r.club_id)] = int(r.n)
    candidates = sorted(set(in_league) | set(guests))
    levels = _levels(conn, world, candidates)
    confed = {c: guests.get(c) or _confederation_of(world, country.get(c, "")) for c in candidates}
    strength = {c: levels.get(c, 0.0) + spec.title_bonus * titles.get(c, 0) for c in candidates}
    chosen: list[Entrant] = []
    taken: set[int] = set()

    def add(club_id: int, how: str) -> None:
        taken.add(club_id)
        chosen.append(Entrant(club_id, confed[club_id] or "UEFA", country.get(club_id, ""), how,
                              strength.get(club_id, 0.0)))

    # UEFA: the Champions League winners, then the coefficient.
    uefa = [c for c in candidates if confed[c] == "UEFA"]
    winners = [c for c in dict.fromkeys(_ucl_winners(conn, world, day)) if c in confed]
    for c in winners[:spec.slots["UEFA"].slots]:
        add(c, "Champions League winners")
    coefficient = coefficients(conn, world, uefa, meta.season_id)
    per: dict[str, int] = {}
    for entrant in chosen:
        per[entrant.country] = per.get(entrant.country, 0) + 1
    cap = spec.slots["UEFA"].per_country
    for c in sorted(uefa, key=lambda x: (-coefficient.get(x, 0.0), x)):
        if sum(1 for e in chosen if e.confederation == "UEFA") >= spec.slots["UEFA"].slots:
            break
        if c in taken or per.get(country.get(c, ""), 0) >= cap:
            continue
        add(c, "UEFA club coefficient")
        per[country.get(c, "")] = per.get(country.get(c, ""), 0) + 1
    # The others: by strength.
    for name, slots in spec.slots.items():
        if name == "UEFA":
            continue
        per = {}
        pool = sorted((c for c in candidates if confed[c] == name),
                      key=lambda x: (-strength[x], x))
        for c in pool:
            if sum(1 for e in chosen if e.confederation == name) >= slots.slots:
                break
            code = country.get(c, "")
            if per.get(code, 0) >= slots.per_country:
                continue
            add(c, "Guest" if c in guests else "Ranking")
            per[code] = per.get(code, 0) + 1
    # The host's best club not already in.
    host = sorted((c for c in candidates if country.get(c) == spec.host and c not in taken),
                  key=lambda x: (-strength[x], x))
    if host:
        add(host[0], "Hosts")
    return chosen


# --- the draw and the tournament ---------------------------------------------------------


def _draw_groups(entrants: list[Entrant], rng: np.random.Generator) -> list[list[Entrant]]:
    """8 groups of 4 from 4 pots by strength: no group with two clubs of one confederation,
    UEFA's at most two. Pot by pot, each club into a random group that still allows it, the
    pot drawn again (up to many times) if it can't be completed."""
    ordered = sorted(entrants, key=lambda e: (-e.strength, e.club_id))
    pots = [ordered[k * 8:(k + 1) * 8] for k in range(4)]

    def allowed(group: list[Entrant], e: Entrant) -> bool:
        same = sum(1 for g in group if g.confederation == e.confederation)
        return same < (2 if e.confederation == "UEFA" else 1)

    for _ in range(500):
        groups: list[list[Entrant]] = [[] for _ in range(8)]
        ok = True
        for pot in pots:
            order = list(pot)
            rng.shuffle(order)
            free = list(range(8))
            for e in order:
                options = [g for g in free if allowed(groups[g], e)]
                if not options:
                    ok = False
                    break
                g = options[int(rng.integers(len(options)))]
                groups[g].append(e)
                free.remove(g)
            if not ok:
                break
        if ok:
            return groups
    raise RuntimeError("no Club World Cup draw satisfies the confederation rules")


def _insert(conn: Connection, meta: CareerMeta, comp: int, stage: str,
            rows: list[tuple[date, int, int, str, int]]) -> None:
    if rows:
        conn.execute(fixture.insert(), [
            {"season_id": meta.season_id, "competition_id": comp, "stage": stage, "round": rnd,
             "tie": tie, "leg": None, "date": day.isoformat(), "home_club_id": home,
             "away_club_id": away, "neutral": 1, "status": "scheduled"}
            for day, home, away, tie, rnd in rows])


def _draw(conn: Connection, world: World, meta: CareerMeta, year: int) -> list[str]:
    spec = world.defs.international.club_world_cup
    entrants = choose_entrants(conn, world, meta, year)
    rng = derive_rng(meta.seed, "cwc-draw", year)
    groups = _draw_groups(entrants, rng)
    comp = competition_id(conn, year)
    days = [_day(year, d) for d in spec.dates.groups]
    rows = []
    for g, members in enumerate(groups):
        a, b, c, d = (e.club_id for e in members)
        for r, pairs in enumerate((((a, b), (c, d)), ((a, c), (d, b)), ((d, a), (b, c)))):
            rows += [(days[r], home, away, LETTERS[g], r + 1) for home, away in pairs]
    _insert(conn, meta, comp, GROUPS, rows)
    _set(conn, _meta_key(year), {
        "entrants": [{"club_id": e.club_id, "confederation": e.confederation,
                      "how": e.how} for e in entrants],
        "paid": []})
    _pay(conn, world, meta, year, [(e.club_id, spec.prizes.participation.get(e.confederation,
                                                                           0.0)) for e in entrants])
    names = {int(r.id): str(r.name) for r in conn.execute(text("SELECT id, name FROM club"))}
    news = [f"The {year} Club World Cup draw: {len(entrants)} clubs in 8 groups, from "
            f"{_day(year, spec.dates.groups[0]).strftime('%-d %B')}."]
    if meta.user_club_id in {e.club_id for e in entrants}:
        group = next(LETTERS[g] for g, m in enumerate(groups)
                     if meta.user_club_id in {e.club_id for e in m})
        rivals = [names[e.club_id] for m in groups for e in m
                  if meta.user_club_id in {x.club_id for x in m} and e.club_id != meta.user_club_id]
        news.append(f"You are in the Club World Cup's Group {group}, with {', '.join(rivals)}.")
    return news


def _pay(conn: Connection, world: World, meta: CareerMeta, year: int,
         amounts: list[tuple[int, float]]) -> None:
    """Prize money to the clubs with finances (guests and national teams have none)."""
    have = {int(r[0]) for r in conn.execute(text("SELECT club_id FROM club_finance"))}
    comp = competition_id(conn, year)
    entries = [Entry(c, "prize", round(amount * 100), comp) for c, amount in amounts
               if amount > 0 and c in have]
    if entries:
        post(conn, meta.current_date, meta.season_id, entries)


@dataclass
class _Row:
    club_id: int
    points: int = 0
    gd: int = 0
    gf: int = 0


def group_tables(conn: Connection) -> dict[str, list[_Row]]:
    rows: dict[str, dict[int, _Row]] = {}
    for f in conn.execute(text("SELECT * FROM fixture WHERE stage = :s ORDER BY id"),
                          {"s": GROUPS}):
        group = rows.setdefault(f.tie, {})
        for c in (f.home_club_id, f.away_club_id):
            group.setdefault(c, _Row(c))
        if f.status != "played":
            continue
        for c, us, them in ((f.home_club_id, f.home_goals, f.away_goals),
                            (f.away_club_id, f.away_goals, f.home_goals)):
            r = group[c]
            r.gf += us
            r.gd += us - them
            r.points += 3 if us > them else 1 if us == them else 0
    return {g: sorted(m.values(), key=lambda r: (-r.points, -r.gd, -r.gf, r.club_id))
            for g, m in sorted(rows.items())}


def _winner(f: Any) -> int | None:
    if f.status != "played":
        return None
    if f.home_goals != f.away_goals:
        return int(f.home_club_id if f.home_goals > f.away_goals else f.away_club_id)
    if f.home_pens is None:
        return None
    return int(f.home_club_id if f.home_pens > f.away_pens else f.away_club_id)


def _round_day(world: World, year: int, rnd: str) -> date:
    dates = world.defs.international.club_world_cup.dates
    return _day(year, {"R16": dates.round_of_16, "QF": dates.quarter_finals,
                       "SF": dates.semi_finals, "F": dates.final}[rnd])


def _progress(conn: Connection, world: World, meta: CareerMeta, year: int) -> list[str]:
    """The next knockout round once the one before is decided; prize money as clubs go on."""
    spec = world.defs.international.club_world_cup
    comp = competition_id(conn, year)
    state = _get(conn, _meta_key(year)) or {}
    paid: list[str] = state.get("paid", [])
    news: list[str] = []
    stages = {r: list(conn.execute(text("SELECT * FROM fixture WHERE stage = :s ORDER BY tie"),
                                   {"s": f"CWC:{r}"}).all()) for r in ROUNDS}
    groups = list(conn.execute(text("SELECT * FROM fixture WHERE stage = :s"),
                               {"s": GROUPS}).all())
    if "groups" not in paid and groups and all(f.status == "played" for f in groups):
        amounts = []
        for f in groups:
            for c, us, them in ((f.home_club_id, f.home_goals, f.away_goals),
                                (f.away_club_id, f.away_goals, f.home_goals)):
                amounts.append((int(c), spec.prizes.win if us > them else
                                spec.prizes.draw if us == them else 0.0))
        _pay(conn, world, meta, year, amounts)
        paid.append("groups")
        tables = group_tables(conn)
        pairs = []
        for k in range(0, 8, 2):
            a, b = tables[LETTERS[k]], tables[LETTERS[k + 1]]
            pairs += [(a[0].club_id, b[1].club_id), (b[0].club_id, a[1].club_id)]
        _insert(conn, meta, comp, "CWC:R16",
                [(_round_day(world, year, "R16"), h, a, str(n + 1), 1)
                 for n, (h, a) in enumerate(pairs)])
        _pay(conn, world, meta, year, [(c, spec.prizes.round_of_16) for p in pairs for c in p])
        stages["R16"] = list(conn.execute(text(
            "SELECT * FROM fixture WHERE stage = 'CWC:R16' ORDER BY CAST(tie AS INTEGER)")).all())
    prize = {"QF": spec.prizes.quarter_finals, "SF": spec.prizes.semi_finals,
             "F": spec.prizes.final}
    for before, after in zip(ROUNDS, ROUNDS[1:], strict=False):
        done = sorted(stages[before], key=lambda f: int(f.tie))
        if not done or stages[after] or any(_winner(f) is None for f in done):
            continue
        winners = [int(w) for f in done if (w := _winner(f)) is not None]
        pairs = [(winners[k], winners[k + 1]) for k in range(0, len(winners), 2)]
        _insert(conn, meta, comp, f"CWC:{after}",
                [(_round_day(world, year, after), h, a, str(n + 1), 1)
                 for n, (h, a) in enumerate(pairs)])
        _pay(conn, world, meta, year, [(c, prize[after]) for p in pairs for c in p])
    final = stages["F"]
    if final and "champions" not in paid and _winner(final[0]) is not None:
        champion = _winner(final[0])
        assert champion is not None
        _pay(conn, world, meta, year, [(champion, spec.prizes.champions)])
        paid.append("champions")
        name = str(conn.execute(text("SELECT name FROM club WHERE id = :c"),
                                {"c": champion}).scalar_one())
        news.append(f"{name} win the {year} FIFA Club World Cup.")
    state["paid"] = paid
    _set(conn, _meta_key(year), state)
    return news


def decider(fx: Any) -> Decider | None:
    """Group matches end as they end; knockouts go to extra time and penalties."""
    return None if fx.stage == GROUPS else Decider(extra_time=True, penalties=True)


def club_world_cup_day(conn: Connection, world: World, meta: CareerMeta, day: date
                       ) -> list[str]:
    """The draw on its day, then the knockouts as the rounds are decided. Returns news."""
    year = edition_on(world, day)
    if year is None:
        return []
    news: list[str] = []
    state = _get(conn, _meta_key(year))
    if state is None:
        if day == draw_date(world, year):
            from footsim.world.international.teams import ensure_international

            ensure_international(conn, world, meta, day)
            news += _draw(conn, world, meta, year)
        return news
    if _day(year, world.defs.international.club_world_cup.dates.groups[0]) <= day:
        news += _progress(conn, world, meta, year)
    return news
