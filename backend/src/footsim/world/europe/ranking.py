"""Country (association) coefficients and the UEFA ranking (W7 A2, docs/plans/w7-all-of-uefa.md).

A club's season points follow UEFA's 2024-27 rules (europe/settings.yaml coefficient). A
country's season coefficient is its clubs' points divided by how many clubs it entered, and its
ranking is the sum of its last five seasons, ties going to the more recent seasons. The seasons
before the career are UEFA's real ones (europe/association_coefficients.yaml); each season played
in the game is added when its last European final is decided.

As UEFA's, a season's access list uses the ranking at the end of the season two before it (2026-27
uses 2020-21 to 2024-25), and the two countries with the best coefficient in the season just
ended each get a European Performance Spot."""

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import Connection, select

from footsim.persistence.schema import (
    association_coefficient,
    club,
    club_coefficient,
    club_league_membership,
    competition,
    continental_entry,
    cup_tie,
    fixture,
    nation,
    season,
)
from footsim.world.context import World
from footsim.world.europe.common import KNOCKOUT, QUALIFYING, competition_id

PERFORMANCE_SPOTS = 2


@dataclass(frozen=True)
class RankRow:
    rank: int
    nation: str  # its code
    seasons: list[float]  # the five seasons' coefficients, oldest first
    total: float


def _start_year(label: str) -> int:
    return int(label.partition("-")[0])


def first_season_label(conn: Connection | None, world: World) -> str:
    """The career's first season ("2026-27"): season 1. Without a career, the season the
    European calendar in the data is for."""
    if conn is not None:
        label = conn.execute(select(season.c.label).where(season.c.id == 1)).scalar()
        if label is not None:
            return str(label)
    return world.defs.europe_calendars[world.defs.europe.calendar].season


def season_id_of(label: str, first_label: str) -> int:
    """A season's id by its label: the career's first season is 1, the one before it 0, and
    so on back."""
    return _start_year(label) - _start_year(first_label) + 1


def season_label_of(season_id: int, first_label: str) -> str:
    start = _start_year(first_label) + season_id - 1
    return f"{start}-{(start + 1) % 100:02d}"


def uefa_nations(world: World) -> list[str]:
    """The associations that take part: UEFA's, those with real coefficients or a league in the
    game (Russia, suspended, has neither)."""
    seeded = {code for values in world.defs.association_coefficients.seasons.values()
              for code in values}
    with_league = {lg.nation for lg in world.defs.leagues.values()}
    return sorted(code for code, n in world.defs.nations.items()
                  if n.confederation == "UEFA" and (code in seeded or code in with_league))


def season_coefficients(conn: Connection | None, world: World) -> dict[int, dict[str, float]]:
    """Every country's coefficient for each season, by season id: the real seasons before the
    career (ids up to 0) and, given a career, those played in it."""
    first = first_season_label(conn, world)
    out: dict[int, dict[str, float]] = {}
    for label, values in world.defs.association_coefficients.seasons.items():
        out[season_id_of(label, first)] = dict(values)
    if conn is not None:
        for row in conn.execute(select(association_coefficient, nation.c.code).join(
                nation, nation.c.id == association_coefficient.c.nation_id)):
            out.setdefault(row.season_id, {})[row.code] = (
                row.points / row.clubs if row.clubs else 0.0)
    return out


def ranking(conn: Connection | None, world: World, through: int) -> list[RankRow]:
    """The ranking at the end of season ``through``: each country's last five seasons summed,
    ties to the more recent seasons, then by code."""
    seasons = world.defs.europe.coefficient.seasons
    window = list(range(through - seasons + 1, through + 1))
    by_season = season_coefficients(conn, world)
    rows = []
    for code in uefa_nations(world):
        values = [by_season.get(s, {}).get(code, 0.0) for s in window]
        rows.append((code, values, sum(values)))
    rows.sort(key=lambda r: (-round(r[2], 3), *(-round(v, 3) for v in reversed(r[1])), r[0]))
    return [RankRow(rank=k, nation=code, seasons=values, total=total)
            for k, (code, values, total) in enumerate(rows, start=1)]


def access_ranking(conn: Connection | None, world: World, season_id: int) -> list[RankRow]:
    """The ranking that sets season ``season_id``'s access list: the one at the end of the
    season two before it."""
    return ranking(conn, world, season_id - 2)


def performance_spots(conn: Connection | None, world: World, season_id: int) -> list[str]:
    """The countries with a European Performance Spot in season ``season_id``: the best two by
    their coefficient in the season before it (ties by five-season ranking)."""
    last = season_coefficients(conn, world).get(season_id - 1, {})
    order = {r.nation: r.rank for r in ranking(conn, world, season_id - 1)}
    best = sorted(uefa_nations(world), key=lambda c: (-last.get(c, 0.0), order.get(c, 99), c))
    return best[:PERFORMANCE_SPOTS]


# --- a season's points --------------------------------------------------------------------

def club_season_points(conn: Connection, world: World, season_id: int) -> dict[int, float]:
    """Every club's coefficient points for a season in Europe (UEFA 2024-27): per match, halved
    in the qualifying and play-off rounds; a league-phase bonus and place bonus; a bonus for each
    knockout round reached from the round of 16."""
    rules = world.defs.europe.coefficient
    points: dict[int, float] = defaultdict(float)
    for comp in world.defs.continental.values():
        comp_id = competition_id(conn, comp)
        for g in conn.execute(select(fixture).where(
                fixture.c.season_id == season_id, fixture.c.stage == comp.key,
                fixture.c.status == "played")):
            factor = rules.qualifying_factor if g.round <= QUALIFYING else 1.0
            for club_id, ours, theirs in ((g.home_club_id, g.home_goals, g.away_goals),
                                          (g.away_club_id, g.away_goals, g.home_goals)):
                earned = rules.win if ours > theirs else rules.draw if ours == theirs else 0.0
                points[club_id] += factor * earned
        place_bonus = rules.ranking_bonus[comp.key]
        for e in conn.execute(select(continental_entry.c.club_id, continental_entry.c.position)
                              .where(continental_entry.c.season_id == season_id,
                                     continental_entry.c.competition_id == comp_id,
                                     continental_entry.c.position.is_not(None))):
            points[e.club_id] += (rules.league_phase_bonus.get(comp.key, 0.0)
                                  + place_bonus.points(e.position))
        bonus = rules.knockout_bonus[comp.key]
        for index in range(1, len(comp.knockout)):  # the round of 16 on (not the play-off)
            for tie in conn.execute(select(cup_tie.c.club_a_id, cup_tie.c.club_b_id).where(
                    cup_tie.c.season_id == season_id, cup_tie.c.competition_id == comp_id,
                    cup_tie.c.round == KNOCKOUT + index)):
                for club_id in (tie.club_a_id, tie.club_b_id):
                    if club_id is not None:
                        points[club_id] += bonus
    return dict(points)


def club_associations(conn: Connection, season_id: int, club_ids: list[int]) -> dict[int, str]:
    """The country each club played for in Europe in a season: the one whose place its entry
    took, else its league's country that season, else its own."""
    if not club_ids:
        return {}
    out: dict[int, str] = {}
    for r in conn.execute(select(continental_entry.c.club_id, continental_entry.c.association)
                          .where(continental_entry.c.season_id == season_id,
                                 continental_entry.c.club_id.in_(club_ids),
                                 continental_entry.c.association.is_not(None))):
        out[r.club_id] = r.association
    missing = [c for c in club_ids if c not in out]
    if missing:
        for r in conn.execute(select(club_league_membership.c.club_id, nation.c.code).join(
                competition, competition.c.id == club_league_membership.c.competition_id).join(
                nation, nation.c.id == competition.c.nation_id).where(
                club_league_membership.c.season_id == season_id,
                club_league_membership.c.club_id.in_(missing))):
            out[r.club_id] = r.code
    missing = [c for c in club_ids if c not in out]
    if missing:
        for r in conn.execute(select(club.c.id, nation.c.code).join(
                nation, nation.c.id == club.c.nation_id).where(club.c.id.in_(missing))):
            out[r.id] = r.code
    return out


def record_season(conn: Connection, world: World, season_id: int) -> None:
    """Once, when the season's last European final is decided: every club's points
    (``club_coefficient``) and every country's season (``association_coefficient``)."""
    if conn.execute(select(club_coefficient.c.club_id).where(
            club_coefficient.c.season_id == season_id)).first() is not None:
        return
    points = club_season_points(conn, world, season_id)
    if not points:
        return
    conn.execute(club_coefficient.insert(), [
        {"club_id": c, "season_id": season_id, "points": p} for c, p in sorted(points.items())])
    countries = club_associations(conn, season_id, sorted(points))
    totals: dict[str, list[float]] = defaultdict(list)
    for club_id, p in points.items():
        if club_id in countries:
            totals[countries[club_id]].append(p)
    ids = {r.code: r.id for r in conn.execute(select(nation.c.id, nation.c.code))}
    rows = [{"nation_id": ids[code], "season_id": season_id, "points": sum(values),
             "clubs": len(values)} for code, values in sorted(totals.items()) if code in ids]
    if rows:
        conn.execute(association_coefficient.insert(), rows)
