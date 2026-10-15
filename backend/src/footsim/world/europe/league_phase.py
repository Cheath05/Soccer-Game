"""The league phase (W6 E3): the pots, the draw and its matchdays, the table, and its money.

**The draw.** Clubs go into pots by coefficient (the Champions League's holders in the first).
Who plays whom comes from a fixed pattern over the pots' places, so every club gets the right
number of opponents from each pot, home and away, and every club plays once each matchday:

- Two opponents from each of four pots (the UCL, the UEL): the pots are paired (A with B, C
  with D). Within a pair, each pot's places form a cycle (place i plays i+1) and each place of
  A meets places i and i+1 of B; those games split into four matchdays (``_block_matchdays``,
  found once by search). The other pot pairs' games are two matchings each, the other four.
- One opponent from each of an even number of pots (the UECL): a matchday within each pot,
  then the pots paired round-robin, one matchday per round.

Home and away: within a pot each club has one of each (the cycle's direction), against each
other pot one of each (two matchings, one hosted by each side); in the one-opponent format
each club hosts half its games (an Euler tour's direction).

Then clubs are placed in their pot's places by a local search that keeps clubs of one country
apart and no club meeting more than two of any country (``MAX_PER_COUNTRY``). The pots, the
pairing, the shifts and the places all come from the career's seed."""

from collections import Counter, defaultdict
from datetime import date
from functools import cache

import numpy as np
from sqlalchemy import Connection, select, update

from footsim.competitions.standings import Result, TableRow, league_table
from footsim.core.rng import derive_rng, derive_seed
from footsim.defs.competitions import PointsRule, Tiebreaker
from footsim.defs.europe import ContinentalDef
from footsim.persistence.schema import club, competition, continental_entry, fixture, nation
from footsim.world.context import World
from footsim.world.cups import make_room, moved_ties_news
from footsim.world.europe.coefficients import coefficients
from footsim.world.europe.common import competition_id, europe_calendar
from footsim.world.finance import Entry, post
from footsim.world.meta import CareerMeta
from footsim.world.squads import club_name

Pos = tuple[int, int]  # (pot, place in it), both from 0
Match = tuple[Pos, Pos]  # (home, away)

MAX_PER_COUNTRY = 2  # opponents from any one country
NODE_LIMIT = 20_000  # search steps placing countries on one pattern before drawing another
PATTERNS = 500  # patterns tried before relaxing the cap on opponents from one country
TIEBREAKERS = [Tiebreaker.POINTS, Tiebreaker.GOAL_DIFFERENCE, Tiebreaker.GOALS_FOR,
               Tiebreaker.AWAY_GOALS_FOR, Tiebreaker.WINS, Tiebreaker.DRAWING_OF_LOTS]
POINTS = PointsRule()


# --- the pattern ------------------------------------------------------------------------------

@cache
def _block_matchdays(n: int, step: int, s: int, t: int
                     ) -> tuple[tuple[tuple[Pos, Pos], ...], ...] | None:
    """Four matchdays for a pair of pots of ``n`` places (pot 0 and pot 1 here), or None if
    this variant has none: each place plays the places ``step`` either side of it in its own
    pot and places i+s and i+t of the other pot, every place once a matchday. Found by a
    depth-first search over perfect matchings in a fixed order, so always the same answer."""
    edges: set[frozenset[Pos]] = set()
    for i in range(n):
        edges.add(frozenset({(0, i), (0, (i + step) % n)}))
        edges.add(frozenset({(1, i), (1, (i + step) % n)}))
        edges.add(frozenset({(0, i), (1, (i + s) % n)}))
        edges.add(frozenset({(0, i), (1, (i + t) % n)}))
    if len(edges) != 4 * n:
        return None  # a step or shift that repeats an opponent
    vertices = sorted({v for e in edges for v in e})

    def matchings(pool: frozenset[frozenset[Pos]]) -> list[frozenset[frozenset[Pos]]]:
        found: list[frozenset[frozenset[Pos]]] = []

        def grow(used: frozenset[Pos], chosen: list[frozenset[Pos]]) -> None:
            free = [v for v in vertices if v not in used]
            if not free:
                found.append(frozenset(chosen))
                return
            v = free[0]
            for e in sorted(pool, key=sorted):
                if v in e and not (e - {v}) & used:
                    grow(used | e, [*chosen, e])

        grow(frozenset(), [])
        return found

    def split(pool: frozenset[frozenset[Pos]], k: int) -> list[frozenset[frozenset[Pos]]] | None:
        if k == 0:
            return [] if not pool else None
        for m in matchings(pool):
            rest = split(pool - m, k - 1)
            if rest is not None:
                return [m, *rest]
        return None

    days = split(frozenset(edges), 4)
    if days is None:
        return None
    return tuple(tuple(_orient(e, n, step, s) for e in sorted(day, key=sorted))
                 for day in days)


def _orient(edge: frozenset[Pos], n: int, step: int, s: int) -> Match:
    """Who's at home: within a pot the place ``step`` before the other (each place hosts one
    and visits one); between the pots, B's place i+s hosts A's place i, and A's place i hosts
    its other opponent in B."""
    a, b = sorted(edge)
    if a[0] == b[0]:
        return (a, b) if b[1] == (a[1] + step) % n else (b, a)
    return (b, a) if b[1] == (a[1] + s) % n else (a, b)


def _block_variant(n: int, rng: np.random.Generator
                   ) -> tuple[tuple[tuple[Pos, Pos], ...], ...]:
    """A random variant of the pot-pair pattern that splits into four matchdays."""
    variants = [(step, s, t) for step in range(1, (n + 1) // 2) for s in range(n)
                for t in range(n) if s < t]
    for k in rng.permutation(len(variants)):
        days = _block_matchdays(n, *variants[k])
        if days is not None:
            return days
    raise ValueError(f"no four matchdays for two pots of {n}")


def _pattern(comp: ContinentalDef, rng: np.random.Generator) -> list[list[Match]]:
    """Every matchday's matches between pot places, in a random order of matchdays."""
    phase = comp.league_phase
    n, pots = phase.pot_size, phase.pots
    days: list[list[Match]] = []
    if phase.per_pot == 2 and pots == 4:
        order = [int(p) for p in rng.permutation(4)]
        (p, q), (r, s) = (order[0], order[1]), (order[2], order[3])
        blocks = [_block_variant(n, rng) for _ in range(2)]
        for k in range(4):
            day: list[Match] = []
            for (first, second), block in zip(((p, q), (r, s)), blocks, strict=True):
                place = {0: first, 1: second}
                day += [((place[h[0]], h[1]), (place[a[0]], a[1])) for h, a in block[k]]
            days.append(day)
        for (x, y), (u, v) in (((p, r), (q, s)), ((p, s), (q, r))):
            shifts = [[int(k) for k in rng.choice(n, 2, replace=False)] for _ in range(2)]
            for leg in (0, 1):
                day = []
                for (one, other), pair_shifts in zip(((x, y), (u, v)), shifts, strict=True):
                    shift = pair_shifts[leg]
                    for i in range(n):
                        a, b = (one, i), (other, (i + shift) % n)
                        day.append((a, b) if leg == 0 else (b, a))
                days.append(day)
    elif phase.per_pot == 1 and pots % 2 == 0 and n % 2 == 0:
        places = [int(k) for k in rng.permutation(pots)]
        own = [((p, i), (p, i + 1)) for p in range(pots) for i in range(0, n, 2)]
        days.append(own)
        ring = places[1:]
        for _ in range(pots - 1):  # the circle method: every pot meets every other once
            pairs = [(places[0], ring[0])] + [(ring[k], ring[-k]) for k in range(1, pots // 2)]
            shift = int(rng.integers(n))
            days.append([((x, i), (y, (i + shift) % n)) for x, y in pairs for i in range(n)])
            ring = ring[-1:] + ring[:-1]
        days = _balance_homes(days)
    else:
        raise ValueError(f"{comp.key}: no draw pattern for {pots} pots and "
                         f"{phase.per_pot} opponents from each")
    return [days[k] for k in rng.permutation(len(days))]


def _balance_homes(days: list[list[Match]]) -> list[list[Match]]:
    """Turn matches round so every place hosts half its games: follow an Euler tour of the
    games (every place plays an even number) and give each game to the place it leaves."""
    adjacency: dict[Pos, list[tuple[Pos, int]]] = defaultdict(list)
    flat = [m for day in days for m in day]
    for k, (h, a) in enumerate(flat):
        adjacency[h].append((a, k))
        adjacency[a].append((h, k))
    used = [False] * len(flat)
    host: dict[int, Pos] = {}
    for start in sorted(adjacency):
        stack = [start]
        while stack:
            v = stack[-1]
            while adjacency[v] and used[adjacency[v][-1][1]]:
                adjacency[v].pop()
            if not adjacency[v]:
                stack.pop()
                continue
            w, k = adjacency[v].pop()
            used[k] = True
            host[k] = v
            stack.append(w)
    out, k = [], 0
    for day in days:
        row = []
        for h, a in day:
            row.append((h, a) if host[k] == h else (a, h))
            k += 1
        out.append(row)
    return out


# --- placing the clubs ------------------------------------------------------------------------

def _neighbours(days: list[list[Match]]) -> dict[Pos, list[Pos]]:
    opponents: dict[Pos, list[Pos]] = defaultdict(list)
    for day in days:
        for h, a in day:
            opponents[h].append(a)
            opponents[a].append(h)
    return opponents


def _broken(layout: list[list[int]], opponents: dict[Pos, list[Pos]],
            country: dict[int, str], cap: int = MAX_PER_COUNTRY) -> int:
    """How many rules a layout breaks: a club meeting its own country, or more than
    MAX_PER_COUNTRY clubs of one."""
    total = 0
    for pos, others in opponents.items():
        mine = country.get(layout[pos[0]][pos[1]], "")
        counts = Counter(country.get(layout[o[0]][o[1]], "") for o in others)
        total += counts.get(mine, 0) + sum(max(0, c - cap) for c in counts.values())
    return total


def _place(pots: list[list[int]], days: list[list[Match]], country: dict[int, str],
           rng: np.random.Generator, cap: int = MAX_PER_COUNTRY
           ) -> tuple[list[list[int]], int]:
    """Clubs in their pots' places so that no club meets a club of its own country, nor more
    than MAX_PER_COUNTRY of any one. A country's clubs in one pot are interchangeable, and a
    country with a single club can break neither rule, so this places countries, not clubs:
    the biggest first, each choosing places none of whose opponents is already beside
    MAX_PER_COUNTRY of its places, and none beside another of its own; a depth-first search
    with backtracking, in a random order, up to NODE_LIMIT steps. The single clubs take the
    places left. Returns the layout and how many rules it breaks (0 unless the search ran out,
    when the clubs are placed at random)."""
    opponents = _neighbours(days)
    by_country: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    for p, pot in enumerate(pots):
        for c in pot:
            by_country[country.get(c, f"#{c}")][p].append(c)
    multi = sorted((code for code, at in by_country.items()
                    if sum(len(v) for v in at.values()) > 1),
                   key=lambda code: (-sum(len(v) for v in by_country[code].values()), code))
    rank = {(p, i): float(rng.random()) for p in range(len(pots)) for i in range(len(pots[p]))}
    taken: set[Pos] = set()
    chosen: dict[str, list[Pos]] = {}
    steps = [0]

    def place_country(k: int) -> bool:
        if k == len(multi):
            return True
        code = multi[k]
        need = [p for p, clubs in sorted(by_country[code].items()) for _ in clubs]
        beside: Counter[Pos] = Counter()  # each place: how many of this country's it meets
        picked: list[Pos] = []

        def pick(j: int) -> bool:
            if j == len(need):
                chosen[code] = list(picked)
                return place_country(k + 1)
            steps[0] += 1
            if steps[0] > NODE_LIMIT:
                return False
            p = need[j]
            after = max((rank[q] for q in picked if q[0] == p), default=-1.0)
            options = sorted(((p, i) for i in range(len(pots[p]))
                              if (p, i) not in taken and rank[(p, i)] > after),
                             key=lambda q: rank[q])
            for pos in options:
                if beside[pos] or any(beside[o] >= cap for o in opponents[pos]):
                    continue
                taken.add(pos)
                picked.append(pos)
                for o in opponents[pos]:
                    beside[o] += 1
                if pick(j + 1):
                    return True
                for o in opponents[pos]:
                    beside[o] -= 1
                picked.pop()
                taken.discard(pos)
            return False

        return pick(0)

    if not place_country(0):
        layout = [[pot[k] for k in rng.permutation(len(pot))] for pot in pots]
        return layout, _broken(layout, opponents, country, cap)
    layout = [[0] * len(pot) for pot in pots]
    for code, places in chosen.items():
        for p in {q[0] for q in places}:
            spots = [q for q in places if q[0] == p]
            clubs = by_country[code][p]
            for q, c in zip(spots, [clubs[k] for k in rng.permutation(len(clubs))], strict=True):
                layout[p][q[1]] = c
    for p, pot in enumerate(pots):
        rest = [c for c in pot if country.get(c, f"#{c}") not in chosen]
        free = [i for i in range(len(pot)) if (p, i) not in taken]
        for i, c in zip(free, [rest[k] for k in rng.permutation(len(rest))], strict=True):
            layout[p][i] = c
    return layout, _broken(layout, opponents, country, cap)


def _draw(comp: ContinentalDef, pots: list[list[int]], country: dict[int, str],
          rng: np.random.Generator) -> tuple[list[list[Match]], list[list[int]]]:
    """A pattern and the clubs' places in it, drawing new patterns until the clubs fit one
    with no rule broken. Should PATTERNS of them all fail (it takes an extreme mix of
    countries), the cap on opponents from one country goes up by one and it tries again; a
    club never meets its own country either way. Failing that too, the attempt that broke
    fewest rules stands."""
    best: tuple[int, list[list[Match]], list[list[int]]] | None = None
    for cap in (MAX_PER_COUNTRY, MAX_PER_COUNTRY + 1):
        for _ in range(PATTERNS):
            days = _pattern(comp, rng)
            layout, broken = _place(pots, days, country, rng, cap)
            if broken == 0:
                return days, layout
            if best is None or broken < best[0]:
                best = (broken, days, layout)
    assert best is not None
    return best[1], best[2]


# --- the draw ---------------------------------------------------------------------------------

def draw_league_phase(conn: Connection, world: World, meta: CareerMeta, comp: ContinentalDef,
                      today: date) -> list[str]:
    """Pots, opponents and matchdays for ``comp``'s league phase, its fixtures, and the
    participation money. Its 36 (or so) entries must all be in."""
    season_id = meta.season_id
    comp_id = competition_id(conn, comp)
    entries = conn.execute(select(continental_entry).where(
        continental_entry.c.season_id == season_id,
        continental_entry.c.competition_id == comp_id,
        continental_entry.c.stage == "league_phase")).all()
    phase = comp.league_phase
    if len(entries) != phase.clubs:
        raise ValueError(f"{comp.key}: {len(entries)} clubs for a league phase of {phase.clubs}")
    clubs = [e.club_id for e in entries]
    coeff = coefficients(conn, world, clubs, season_id)
    holders = {e.club_id for e in entries if e.route == f"holder:{comp.key}"}
    ranked = sorted(clubs, key=lambda c: (c not in holders, -coeff[c], c))
    pots = [ranked[k * phase.pot_size:(k + 1) * phase.pot_size] for k in range(phase.pots)]
    country = {r.id: r.code for r in conn.execute(
        select(club.c.id, nation.c.code).join(nation, nation.c.id == club.c.nation_id)
        .where(club.c.id.in_(clubs)))}
    rng = derive_rng(meta.seed, "europe-league-phase", season_id, comp.key)
    days, layout = _draw(comp, pots, country, rng)
    for p, pot in enumerate(layout):
        conn.execute(update(continental_entry).where(
            continental_entry.c.season_id == season_id,
            continental_entry.c.club_id.in_(pot)).values(pot=p + 1))
    dates = europe_calendar(world, season_id).competitions[comp.key].league_phase
    moved: list[int] = []
    for matchday, (day, matchday_dates) in enumerate(zip(days, dates, strict=True), start=1):
        for k, (home, away) in enumerate(day):
            when = matchday_dates[k % len(matchday_dates)]
            home_club, away_club = layout[home[0]][home[1]], layout[away[0]][away[1]]
            conn.execute(fixture.insert().values(
                season_id=season_id, competition_id=comp_id, stage=comp.key, round=matchday,
                tie=None, leg=None, date=when.isoformat(), home_club_id=home_club,
                away_club_id=away_club, neutral=0, status="scheduled"))
            for club_id in (home_club, away_club):
                moved += make_room(conn, world, club_id, when, today)
    prize = world.defs.finance.europe_prizes[comp.key]
    post(conn, today, season_id, [Entry(c, "prize", round(prize.participation * 100), comp_id)
                                  for c in clubs])
    return (_draw_news(conn, meta, comp, layout, days, dates)
            + moved_ties_news(conn, world, meta, moved))


def league_phase_done(conn: Connection, season_id: int, comp: ContinentalDef) -> bool:
    """Every league-phase match played (and there were some)."""
    games = conn.execute(select(fixture.c.status).where(
        fixture.c.season_id == season_id, fixture.c.stage == comp.key,
        fixture.c.round.between(1, comp.league_phase.matches))).all()
    return bool(games) and all(g.status == "played" for g in games)


def table(conn: Connection, meta: CareerMeta, season_id: int, comp: ContinentalDef
          ) -> list[TableRow]:
    """The league-phase table so far."""
    clubs = [r.club_id for r in conn.execute(
        select(continental_entry.c.club_id).join(
            competition, competition.c.id == continental_entry.c.competition_id).where(
            continental_entry.c.season_id == season_id, competition.c.key == comp.key,
            continental_entry.c.stage == "league_phase"))]
    results = [Result(r.home_club_id, r.away_club_id, r.home_goals, r.away_goals)
               for r in conn.execute(select(fixture).where(
                   fixture.c.season_id == season_id, fixture.c.stage == comp.key,
                   fixture.c.round.between(1, comp.league_phase.matches),
                   fixture.c.status == "played"))]
    return league_table(sorted(clubs), results, POINTS, TIEBREAKERS,
                        derive_seed(meta.seed, "europe-lots", season_id, comp.key))


def finish_league_phase(conn: Connection, world: World, meta: CareerMeta,
                        comp: ContinentalDef, today: date) -> list[TableRow]:
    """Record the final positions and pay for the wins and draws."""
    rows = table(conn, meta, meta.season_id, comp)
    for row in rows:
        conn.execute(update(continental_entry).where(
            continental_entry.c.season_id == meta.season_id,
            continental_entry.c.club_id == row.club_id).values(position=row.position))
    prize = world.defs.finance.europe_prizes[comp.key]
    comp_id = competition_id(conn, comp)
    post(conn, today, meta.season_id, [
        Entry(row.club_id, "prize", round((row.won * prize.win + row.drawn * prize.draw) * 100),
              comp_id) for row in rows])
    return rows


def _draw_news(conn: Connection, meta: CareerMeta, comp: ContinentalDef,
               layout: list[list[int]], days: list[list[Match]],
               dates: list[list[date]]) -> list[str]:
    user = meta.user_club_id
    where = next(((p, i) for p, pot in enumerate(layout) for i, c in enumerate(pot) if c == user),
                 None)
    if user is None or where is None:
        return []
    games = []
    for day, matchday_dates in zip(days, dates, strict=True):
        for k, (home, away) in enumerate(day):
            if where in (home, away):
                other = away if home == where else home
                rival = club_name(conn, layout[other[0]][other[1]])
                when = matchday_dates[k % len(matchday_dates)]
                games.append(f"{rival} ({'h' if home == where else 'a'}, {when:%d %b})")
    return [f"{comp.name} league phase draw for {club_name(conn, user)} (pot {where[0] + 1}): "
            + ", ".join(games) + "."]

