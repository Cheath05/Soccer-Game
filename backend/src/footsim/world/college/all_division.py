"""The All-Division Tournament (22 Nov; ``all_division`` in data/config/college/lower.yaml): once
D-I's College Cup and the D-II and D-III finals are played, each division's best meet in one
knockout to settle which is the best team in college soccer.

A division's champion is its first entrant, then its best by the season's final RPI. The best
enter latest: with the shipped rules D-I's top four have two byes, D-I's next four and the top
four of D-II and D-III one. The field is seeded as one list (the later a team enters, the better
its seed; within a round's entrants, by place among its division's that round, D-I before D-II
before D-III: D-I's 9th, D-II's 5th, D-III's 5th, D-I's 10th...). Each round
is drawn when the one before it ends: the best seed left meets the worst left from another
division (or the worst left, when only one division is), the better seed at home until
``neutral_from``; extra time, then penalties.

It's a competition of its own (type ``college_all``), so its games count in no division's
table, RPI or record. Its fixtures' stage and its entries' event are ``ADT``; an entry's ``bid``
is the team's division (1, 2 or 3) and its ``rank`` its place in that division. Only a career
with Divisions II and III has it (a college coach's). The user's own games are played like any
other; the rest are quick results."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Connection, Row, select

from footsim.competitions.college import ranked
from footsim.defs.college import AllDivisionDef, on
from footsim.persistence.schema import competition, fixture, league_title
from footsim.world.college import lower
from footsim.world.college.common import ALL_DIVISION, ALL_TYPE
from footsim.world.college.season import (
    NATIONAL_TITLE,
    _club_name,
    _knockout_winner,
    _season_start,
    _seed,
    _title,
    college_competition,
    entries,
    rankings,
)
from footsim.world.context import World
from footsim.world.meta import CareerMeta

TITLE = "All-Division Tournament"  # its title in league_title


def rules(world: World) -> AllDivisionDef | None:
    defs = lower.rules(world)
    return defs.all_division if defs is not None else None


def competition_id(conn: Connection, world: World) -> int | None:
    """The tournament's competition, once the career has it."""
    adt = rules(world)
    if adt is None:
        return None
    found = conn.execute(select(competition.c.id).where(competition.c.key == adt.key,
                                                        competition.c.type == ALL_TYPE)).scalar()
    return int(found) if found is not None else None


def _ensure(conn: Connection, world: World) -> int | None:
    """The tournament's competition, created for a career with the lower divisions."""
    adt = rules(world)
    found = competition_id(conn, world)
    if adt is None or found is not None:
        return found
    divisions = lower.competitions(conn, world)
    if not divisions:
        return None
    nation = conn.execute(select(competition.c.nation_id).where(
        competition.c.id == next(iter(divisions.values())))).scalar()
    inserted = conn.execute(competition.insert().values(
        key=adt.key, name=adt.name, short_name=adt.short_name, nation_id=nation, type=ALL_TYPE,
        tier=None, sim_level="simulated"))
    assert inserted.inserted_primary_key is not None
    return int(inserted.inserted_primary_key[0])


# --- the field ----------------------------------------------------------------------------------


def _national_champion(conn: Connection, comp: int, season_id: int, title: str) -> int | None:
    found = conn.execute(select(league_title.c.club_id).where(
        league_title.c.season_id == season_id, league_title.c.competition_id == comp,
        league_title.c.title == title)).scalar()
    return int(found) if found is not None else None


def _division_orders(conn: Connection, world: World, season_id: int
                     ) -> dict[int, list[int]] | None:
    """Each division's teams in the tournament's order (its champion first, then by the RPI);
    None while a national final is still to be played."""
    d1 = college_competition(conn, world)
    defs = lower.rules(world)
    if d1 is None or defs is None:
        return None
    found = {1: (_national_champion(conn, d1, season_id, NATIONAL_TITLE),
                 ranked(rankings(conn, world, season_id)))}
    for division, comp in lower.competitions(conn, world).items():
        found[division] = (
            _national_champion(conn, comp, season_id,
                               lower._division_title(defs.divisions[division])),
            lower.ranking(conn, world, division, season_id))
    orders = {}
    for division, (champion, order) in found.items():
        if champion is None:
            return None
        orders[division] = [champion] + [c for c in order if c != champion]
    return orders


@dataclass(frozen=True)
class Entrant:
    seed: int  # 1 the best, across the divisions
    club_id: int
    division: int
    rank: int  # in its division (1 its champion)
    enters: int  # the round it starts in (0 the first)


def select_field(conn: Connection, world: World, meta: CareerMeta) -> list[str]:
    """The field, seeded; nothing (and no field) while a national final is still to be played.
    Returns news."""
    adt = rules(world)
    comp = _ensure(conn, world)
    orders = _division_orders(conn, world, meta.season_id)
    if adt is None or comp is None or orders is None:
        return []
    picked = []  # (round it enters, place among its division's entrants that round, ...)
    for division, counts in adt.entries.items():
        order = orders.get(division, [])
        for rank, club_id in enumerate(order[:sum(counts)], start=1):
            enters = adt.entry_round(division, rank)
            place = rank - sum(counts[enters + 1:])
            picked.append((enters, place, division, rank, club_id))
    if sum(adt.field_size(d) for d in adt.entries) != len(picked):
        return []  # a division too small for its places: no tournament this year
    picked.sort(key=lambda p: (-p[0], p[1], p[2]))
    clubs = [p[4] for p in picked]
    _seed(conn, meta.season_id, ALL_DIVISION, clubs, {p[4]: str(p[2]) for p in picked}, None,
          {p[4]: p[3] for p in picked})
    top = _club_name(conn, clubs[0])
    sizes = ", ".join(f"{adt.field_size(d)} from {division_name(world, d)}"
                      for d in sorted(adt.entries))
    return [f"The {adt.name}'s field of {len(clubs)} is out: {sizes}, to settle the best team in "
            f"college soccer. {top} are the top seed."]


def division_name(world: World, division: int) -> str:
    defs = lower.rules(world)
    if division == 1 or defs is None or division not in defs.divisions:
        return "D-I"
    return defs.divisions[division].short_name.removeprefix("NCAA ")


def field(conn: Connection, world: World, season_id: int) -> list[Entrant]:
    """The season's field, by seed (empty before it's picked)."""
    from footsim.persistence.schema import college_entry

    adt = rules(world)
    if adt is None:
        return []
    return [Entrant(seed=int(r.seed), club_id=int(r.club_id), division=int(r.bid),
                    rank=int(r.rank), enters=adt.entry_round(int(r.bid), int(r.rank)))
            for r in conn.execute(select(college_entry).where(
                college_entry.c.season_id == season_id,
                college_entry.c.event == ALL_DIVISION).order_by(college_entry.c.seed))]


# --- the rounds ---------------------------------------------------------------------------------


def draw(teams: list[Entrant]) -> list[tuple[Entrant, Entrant]]:
    """A round's pairs, the better seed first: the best left meets the worst left from another
    division, or the worst left when there's none."""
    left = sorted(teams, key=lambda e: e.seed)
    pairs = []
    while len(left) >= 2:
        best = left.pop(0)
        other = [e for e in left if e.division != best.division]
        rival = (other or left)[-1]
        left.remove(rival)
        pairs.append((best, rival))
    return pairs


@dataclass(frozen=True)
class Match:
    round: int
    index: int
    a: Entrant  # the better seed: at home unless it's neutral
    b: Entrant
    fixture: Row[Any]
    winner: Entrant | None


def matches(conn: Connection, world: World, season_id: int) -> tuple[list[Entrant], list[Match]]:
    """The field and every match drawn so far, round by round."""
    teams = field(conn, world, season_id)
    comp = competition_id(conn, world)
    if not teams or comp is None:
        return teams, []
    by_club = {e.club_id: e for e in teams}
    out = []
    for r in conn.execute(select(fixture).where(
            fixture.c.season_id == season_id, fixture.c.competition_id == comp,
            fixture.c.stage == ALL_DIVISION).order_by(fixture.c.round, fixture.c.id)):
        a, b = by_club[int(r.home_club_id)], by_club[int(r.away_club_id)]
        if b.seed < a.seed:
            a, b = b, a
        won = _knockout_winner(r)
        out.append(Match(int(r.round), int(r.tie), a, b, r,
                         by_club[won] if won is not None else None))
    return teams, out


def _advance(conn: Connection, world: World, meta: CareerMeta, comp: int, day: date
             ) -> int | None:
    """Draw the next round once the one before it is over; the champion's club once decided."""
    adt = rules(world)
    assert adt is not None
    teams, played = matches(conn, world, meta.season_id)
    start = _season_start(conn, meta.season_id)
    winners: list[Entrant] = []
    for k in range(len(adt.rounds)):
        games = [m for m in played if m.round == k]
        if games:
            if any(m.winner is None for m in games):
                return None  # still being played
            winners = [m.winner for m in games if m.winner is not None]
            continue
        playing = [e for e in teams if e.enters == k] + winners
        when = max(on(adt.rounds[k], start), day + timedelta(days=1))
        neutral = k >= adt.neutral_from
        conn.execute(fixture.insert(), [
            {"season_id": meta.season_id, "competition_id": comp, "stage": ALL_DIVISION,
             "round": k, "tie": str(index), "leg": None, "date": when.isoformat(),
             "home_club_id": a.club_id, "away_club_id": b.club_id, "neutral": int(neutral),
             "status": "scheduled"}
            for index, (a, b) in enumerate(draw(playing))])
        return None
    return winners[0].club_id if len(winners) == 1 else None


def progress_all_division(conn: Connection, world: World, meta: CareerMeta, day: date
                          ) -> list[str]:
    """A day of the tournament: its field once every national final is played (from
    ``selection``), each round's draw, and its champion. Returns news."""
    adt = rules(world)
    if adt is None or not lower.competitions(conn, world):
        return []
    comp = competition_id(conn, world)
    if comp is not None and _national_champion(conn, comp, meta.season_id, TITLE) is not None:
        return []  # this season's is over
    news: list[str] = []
    if not entries(conn, meta.season_id, ALL_DIVISION):
        if day < on(adt.selection, _season_start(conn, meta.season_id)):
            return []
        news += select_field(conn, world, meta)
        comp = competition_id(conn, world)
        if comp is None or not entries(conn, meta.season_id, ALL_DIVISION):
            return news
    assert comp is not None
    won = _advance(conn, world, meta, comp, day)
    if won is not None and _title(conn, comp, meta.season_id, TITLE, won, "champion",
                                  ALL_DIVISION, day):
        division = next(e.division for e in field(conn, world, meta.season_id)
                        if e.club_id == won)
        news.append(f"{_club_name(conn, won)} ({division_name(world, division)}) are the "
                    f"All-Division champions: the best team in college soccer this season.")
    return news


def run(conn: Connection, world: World, season_id: int, club_id: int) -> str | None:
    """A team's tournament this season, in words (None if it isn't in the field)."""
    adt = rules(world)
    teams, played = matches(conn, world, season_id)
    mine = next((e for e in teams if e.club_id == club_id), None)
    if adt is None or mine is None:
        return None
    games = [m for m in played if club_id in (m.a.club_id, m.b.club_id)]
    if not games:
        return f"All-Division Tournament: starts in the {adt.round_names[mine.enters]}"
    last = max(games, key=lambda m: m.round)
    name = adt.round_names[last.round]
    if last.winner is None:
        return f"All-Division Tournament: {name} next"
    if last.winner.club_id != club_id:
        return f"All-Division Tournament: out in the {name}"
    if last.round == len(adt.rounds) - 1:
        return "All-Division champions"
    return f"All-Division Tournament: through the {name}"
