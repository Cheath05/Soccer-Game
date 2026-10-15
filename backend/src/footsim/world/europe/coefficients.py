"""Club coefficients (UEFA's, europe/settings.yaml coefficient): the points a club has earned in
Europe in each of the last five seasons, summed, and never less than 20% of its country's
five-season coefficient (UEFA's floor). Seasons before the career count a share of a figure from
the club's reputation, so the first seasons' seeding looks like real football's, and that share
fades out as the club's own results come in."""

from sqlalchemy import Connection, select

from footsim.persistence.schema import club, club_coefficient, club_league_membership, competition
from footsim.persistence.schema import nation as nation_table
from footsim.world.context import World
from footsim.world.europe.ranking import ranking


def reputation_seed(world: World, reputation: float) -> float:
    rules = world.defs.europe.coefficient
    return max(0.0, (reputation - rules.reputation_floor) * rules.reputation_per_point)


def club_nations(conn: Connection, club_ids: list[int], season_id: int) -> dict[int, str]:
    """Each club's country: its league's that season, else its own."""
    out = {r.club_id: r.code for r in conn.execute(
        select(club_league_membership.c.club_id, nation_table.c.code).join(
            competition, competition.c.id == club_league_membership.c.competition_id).join(
            nation_table, nation_table.c.id == competition.c.nation_id).where(
            club_league_membership.c.season_id == season_id,
            club_league_membership.c.club_id.in_(club_ids)))}
    missing = [c for c in club_ids if c not in out]
    if missing:
        out |= {r.id: r.code for r in conn.execute(select(club.c.id, nation_table.c.code).join(
            nation_table, nation_table.c.id == club.c.nation_id).where(club.c.id.in_(missing)))}
    return out


def coefficients(conn: Connection, world: World, club_ids: list[int], season_id: int
                 ) -> dict[int, float]:
    """Each club's coefficient going into season ``season_id``: its points over the
    ``seasons`` before it (a season before the career counting seed / seasons), and at least
    ``association_share`` of its country's five-season coefficient."""
    rules = world.defs.europe.coefficient
    window = range(season_id - rules.seasons, season_id)
    earned: dict[int, float] = {c: 0.0 for c in club_ids}
    reputation: dict[int, float] = {}
    countries: dict[int, str] = {}
    if club_ids:
        for row in conn.execute(select(club_coefficient).where(
                club_coefficient.c.club_id.in_(club_ids),
                club_coefficient.c.season_id.in_(list(window)))):
            earned[row.club_id] += row.points
        reputation = {r.id: r.reputation for r in conn.execute(
            select(club.c.id, club.c.reputation).where(club.c.id.in_(club_ids)))}
        countries = club_nations(conn, club_ids, season_id)
    floors = {r.nation: r.total * rules.association_share
              for r in ranking(conn, world, season_id - 1)} if club_ids else {}
    before = sum(1 for s in window if s < 1)
    return {c: max(earned[c] + reputation_seed(world, reputation.get(c, 0)) * before
                   / rules.seasons, floors.get(countries.get(c, ""), 0.0))
            for c in club_ids}
