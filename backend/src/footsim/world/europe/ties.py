"""Two-legged and one-match ties, as the European rounds use them: their rows and fixtures,
and who won them."""

from datetime import date
from typing import Any

from sqlalchemy import Connection, Row, select

from footsim.persistence.schema import cup_tie, fixture
from footsim.world.context import World
from footsim.world.cups import make_room


def insert_ties(conn: Connection, world: World, season_id: int, comp_id: int, comp_key: str,
                round_number: int, ties: list[tuple[int, int]], days: list[list[date]],
                neutral: bool, today: date) -> list[int]:
    """The ties' rows and fixtures: club A at home in the first leg, B in the second. Each leg's
    matches are spread over its days in turn; a club's league matches and cup ties too close
    are moved (the cup matches moved are returned, for the news)."""
    moved: list[int] = []
    conn.execute(cup_tie.insert(), [
        {"season_id": season_id, "competition_id": comp_id, "round": round_number,
         "tie": str(n), "club_a_id": a, "club_b_id": b, "winner_club_id": None}
        for n, (a, b) in enumerate(ties, start=1)])
    for n, (a, b) in enumerate(ties, start=1):
        legs = [(a, b)] if len(days) == 1 else [(a, b), (b, a)]
        for leg, ((home, away), leg_days) in enumerate(zip(legs, days, strict=True), start=1):
            day = leg_days[(n - 1) % len(leg_days)]
            conn.execute(fixture.insert().values(
                season_id=season_id, competition_id=comp_id, stage=comp_key, round=round_number,
                tie=str(n), leg=leg if len(days) == 2 else None, date=day.isoformat(),
                home_club_id=home, away_club_id=away, neutral=int(neutral), status="scheduled"))
            for club_id in (home, away):
                moved += make_room(conn, world, club_id, day, today)
    return moved


def tie_winner(conn: Connection, season_id: int, comp_key: str, tie: Row[Any]) -> int | None:
    """Who won a two-legged or one-match tie, once it's all played: on aggregate, then the
    second leg's penalties (no away goals)."""
    games = conn.execute(select(fixture).where(
        fixture.c.season_id == season_id, fixture.c.stage == comp_key,
        fixture.c.round == tie.round, fixture.c.tie == tie.tie).order_by(fixture.c.leg)).all()
    if not games or any(g.status != "played" for g in games):
        return None
    goals = {tie.club_a_id: 0, tie.club_b_id: 0}
    for g in games:
        goals[g.home_club_id] += g.home_goals
        goals[g.away_club_id] += g.away_goals
    if goals[tie.club_a_id] != goals[tie.club_b_id]:
        return int(max(goals, key=lambda c: goals[c]))
    last = games[-1]
    if last.home_pens is None:
        return None
    return int(last.home_club_id if last.home_pens > last.away_pens else last.away_club_id)
