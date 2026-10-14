"""Club coefficients (simplified UEFA, europe/settings.yaml coefficient): the points a club has
earned in Europe in each of the last few seasons, summed. Seasons before the career began
count a share of a figure from the club's reputation, so the first seasons' pots look like
real ones, and that share fades out as the club's own results come in."""

from sqlalchemy import Connection, select

from footsim.persistence.schema import club, club_coefficient
from footsim.world.context import World


def reputation_seed(world: World, reputation: float) -> float:
    rules = world.defs.europe.coefficient
    return max(0.0, (reputation - rules.reputation_floor) * rules.reputation_per_point)


def coefficients(conn: Connection, world: World, club_ids: list[int], season_id: int
                 ) -> dict[int, float]:
    """Each club's coefficient going into season ``season_id``: its points over the
    ``seasons`` before it, a season before the career counting seed / seasons."""
    rules = world.defs.europe.coefficient
    window = range(season_id - rules.seasons, season_id)
    earned: dict[int, float] = {c: 0.0 for c in club_ids}
    reputation: dict[int, float] = {}
    if club_ids:
        for row in conn.execute(select(club_coefficient).where(
                club_coefficient.c.club_id.in_(club_ids),
                club_coefficient.c.season_id.in_(list(window)))):
            earned[row.club_id] += row.points
        reputation = {r.id: r.reputation for r in conn.execute(
            select(club.c.id, club.c.reputation).where(club.c.id.in_(club_ids)))}
    before = sum(1 for s in window if s < 1)
    return {c: earned[c] + reputation_seed(world, reputation.get(c, 0)) * before / rules.seasons
            for c in club_ids}
