"""Who plays in Europe each season (europe/access.yaml): places by league finish, cup and title,
handed out from the top competition down, each club in the highest it earns.

A country's order is last season's table of its top league. In the first season, or for a
league new to the career, it's the league's clubs by reputation (as the domestic cups seed).
A country with clubs in the world but no league in the game puts its clubs in order by a
lottery each season, weighted by reputation (europe/settings.yaml lottery_power).

A place whose club is already placed passes down the table: a league place to the next club
of that country not yet in Europe, a cup winner's to the best-placed club of the cup country's
top league not yet in. A place nobody can take (no holder yet, no such club) is filled once
the stage's other places are: the first goes to the competition's first ``fill`` country's
next club, the second to the second's, and so on in turn."""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from sqlalchemy import Connection, select

from footsim.core.rng import derive_rng
from footsim.defs.europe import PlaceDef
from footsim.persistence.schema import (
    club,
    club_league_membership,
    competition,
    cup_tie,
    league_final,
    nation,
)
from footsim.world.context import World
from footsim.world.europe.common import KNOCKOUT, competitions_by_rank
from footsim.world.meta import CareerMeta


@dataclass(frozen=True)
class Entry:
    competition: str  # UCL, UEL, UECL
    club_id: int
    stage: str  # league_phase | qualifying
    route: str  # league:ENG:4, cup:FA_CUP, holder:UCL, fill:ENG


def _top_league_key(world: World, nation_code: str) -> str | None:
    return next((key for key, lg in world.defs.leagues.items()
                 if lg.nation == nation_code and lg.tier == 1), None)


def nation_order(conn: Connection, world: World, meta: CareerMeta, season_id: int,
                 nation_code: str) -> list[int]:
    """The country's clubs in the order its places go: last season's top-league table, its
    clubs by reputation when there's no table yet, or a lottery when the country has no league
    in the career."""
    key = _top_league_key(world, nation_code)
    comp = (conn.execute(select(competition.c.id).where(competition.c.key == key)).first()
            if key is not None else None)
    if comp is not None:
        table = [r.club_id for r in conn.execute(select(league_final).where(
            league_final.c.season_id == season_id - 1,
            league_final.c.competition_id == comp.id).order_by(league_final.c.position))]
        if table:
            return table
        return [r.id for r in conn.execute(
            select(club.c.id).join(club_league_membership,
                                   club_league_membership.c.club_id == club.c.id)
            .where(club_league_membership.c.season_id == season_id,
                   club_league_membership.c.competition_id == comp.id)
            .order_by(club.c.reputation.desc(), club.c.id))]
    return _lottery(conn, world, meta, season_id, nation_code)


def _lottery(conn: Connection, world: World, meta: CareerMeta, season_id: int,
             nation_code: str) -> list[int]:
    """A country without a league: its clubs (those in no league this season) in a weighted
    lottery order, each draw's chances weighted by reputation ** lottery_power."""
    in_league = select(club_league_membership.c.club_id).where(
        club_league_membership.c.season_id == season_id)
    rows = conn.execute(select(club.c.id, club.c.reputation).join(
        nation, nation.c.id == club.c.nation_id).where(
        nation.c.code == nation_code, club.c.id.not_in(in_league)).order_by(club.c.id)).all()
    if not rows:
        return []
    top = max(max(r.reputation for r in rows), 1)
    weights = np.array([(max(r.reputation, 1) / top) ** world.defs.europe.lottery_power
                        for r in rows])
    rng = derive_rng(meta.seed, "europe-lottery", season_id, nation_code)
    # Weighted sampling without replacement (Efraimidis and Spirakis): sort by u ** (1 / w).
    keys = np.log(rng.random(len(rows))) / weights
    return [rows[k].id for k in np.argsort(-keys, kind="stable")]


def _final_winner(conn: Connection, season_id: int, competition_key: str,
                  final_round: int) -> int | None:
    row = conn.execute(select(cup_tie.c.winner_club_id).join(
        competition, competition.c.id == cup_tie.c.competition_id).where(
        competition.c.key == competition_key, cup_tie.c.season_id == season_id,
        cup_tie.c.round == final_round, cup_tie.c.winner_club_id.is_not(None))).first()
    return int(row.winner_club_id) if row is not None else None


def cup_winner(conn: Connection, world: World, season_id: int, cup_key: str) -> int | None:
    """Who won a domestic cup's final in season ``season_id``."""
    cup = world.defs.cups.get(cup_key)
    if cup is None:
        return None
    return _final_winner(conn, season_id, cup_key, len(cup.rounds) - 1)


def holder(conn: Connection, world: World, season_id: int, comp_key: str) -> int | None:
    """Who won a European competition's final in season ``season_id``."""
    comp = world.defs.continental[comp_key]
    return _final_winner(conn, season_id, comp_key, KNOCKOUT + len(comp.knockout) - 1)


def qualify(conn: Connection, world: World, meta: CareerMeta, season_id: int) -> list[Entry]:
    """Every club's European place for season ``season_id``: the league phase or the summer
    play-off round of one competition, from last season's tables, cups and finals."""
    orders: dict[str, list[int]] = {}

    def order(code: str) -> list[int]:
        if code not in orders:
            orders[code] = nation_order(conn, world, meta, season_id, code)
        return orders[code]

    placed: dict[int, Entry] = {}

    def free(code: str, rank: int) -> tuple[int, int] | None:
        """The first club of the country not yet placed, from ``rank`` down, and its rank."""
        clubs = order(code)
        for index in range(rank - 1, len(clubs)):
            if clubs[index] not in placed:
                return clubs[index], index + 1
        return None

    for comp in competitions_by_rank(world):
        rules = world.defs.europe_access.competitions[comp.key]
        first = [p for p in rules.league_phase if p.holder is not None]
        rest = [p for p in rules.league_phase if p.holder is None]
        turn = 0  # the next fill country, in turn across the competition's vacancies
        for stage, places in (("league_phase", first + rest), ("qualifying", rules.qualifying)):
            vacant = 0
            for place in places:
                for slot in range(place.count):
                    found = _resolve(conn, world, season_id, place, slot, placed, free)
                    if found is None:
                        vacant += 1
                    else:
                        placed[found[0]] = Entry(comp.key, found[0], stage, found[1])
            for _ in range(vacant):
                for _ in range(len(rules.fill)):
                    code = rules.fill[turn % len(rules.fill)]
                    turn += 1
                    found_fill = free(code, 1)
                    if found_fill is not None:
                        placed[found_fill[0]] = Entry(comp.key, found_fill[0], stage,
                                                      f"fill:{code}")
                        break
    return list(placed.values())


def _resolve(conn: Connection, world: World, season_id: int, place: PlaceDef, slot: int,
             placed: dict[int, Entry],
             free: Callable[[str, int], tuple[int, int] | None]) -> tuple[int, str] | None:
    if place.holder is not None:
        winner = holder(conn, world, season_id - 1, place.holder)
        if winner is not None and winner not in placed:
            return winner, f"holder:{place.holder}"
        return None
    if place.cup is not None:
        winner = cup_winner(conn, world, season_id - 1, place.cup)
        if winner is not None and winner not in placed:
            return winner, f"cup:{place.cup}"
        code = place.nation or world.defs.cups[place.cup].nation
        found = free(code, 1)
        return (found[0], f"league:{code}:{found[1]}") if found is not None else None
    assert place.nation is not None and place.ranks is not None
    found = free(place.nation, place.ranks[0] + slot)
    return (found[0], f"league:{place.nation}:{found[1]}") if found is not None else None


@dataclass(frozen=True)
class Place:
    """A European place one country's clubs can earn: a run of its top league's finishes, or
    a domestic cup's win."""
    competition: str  # UCL, UEL, UECL
    stage: str  # league_phase | qualifying
    ranks: tuple[int, int] | None
    cup: str | None


def country_places(world: World, nation_code: str) -> list[Place]:
    """The places a country's clubs earn by the access list, from the top competition down:
    as written, before any pass down the table (a club earning two takes the higher, and its
    other goes to the next club not yet in Europe) or extra places fill vacancies."""
    places = []
    for comp in competitions_by_rank(world):
        rules = world.defs.europe_access.competitions[comp.key]
        for stage, listed in (("league_phase", rules.league_phase),
                              ("qualifying", rules.qualifying)):
            places += [Place(comp.key, stage, p.ranks, p.cup) for p in listed
                       if p.nation == nation_code and (p.ranks or p.cup)]
    return places


def route_nation(world: World, route: str) -> str | None:
    """The country whose place a route is: league:ENG:4 and fill:ENG are England's, cup:FA_CUP
    the cup's country's; a holder's is its league's (None here)."""
    kind, _, rest = route.partition(":")
    if kind in ("league", "fill"):
        return rest.partition(":")[0] or None
    if kind == "cup":
        cup = world.defs.cups.get(rest)
        return cup.nation if cup else None
    return None
