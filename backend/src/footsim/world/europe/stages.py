"""A European season's stages, as the days come (W6, W7): when the season starts, the entries
and the first qualifying rounds' draws; through the summer, the qualifying rounds settled and the
next ones drawn as they're decided (qualifying.py); once every qualifying round is over, the
league phases' draws; then the league phases and the knockouts (W6 E3, E4).

Ties use the domestic cups' machinery: ``cup_tie`` rows, fixtures with ``leg`` 1 and 2, the
Decider for extra time and penalties, and moving a club's league matches out of the way."""

from datetime import date
from typing import Any

from sqlalchemy import Connection, Row, select

from footsim.match.report import Decider
from footsim.persistence.schema import continental_entry, fixture
from footsim.world.context import World
from footsim.world.europe.common import (
    KNOCKOUT,
    QUALIFYING,
    competition_id,
    competitions_by_rank,
    enabled,
    qualifying_round,
)
from footsim.world.europe.knockout import progress_knockout
from footsim.world.europe.league_phase import (
    draw_league_phase,
    finish_league_phase,
    league_phase_done,
)
from footsim.world.europe.qualifying import qualifying_done, settle, start_qualifying
from footsim.world.meta import CareerMeta
from footsim.world.squads import club_name


def start_europe(conn: Connection, world: World, meta: CareerMeta, season_id: int,
                 today: date) -> list[str]:
    """The season's European entries and the first qualifying rounds' draws. Nothing when the
    European competitions are switched off, or already started."""
    if not enabled(world) or conn.execute(select(continental_entry.c.id).where(
            continental_entry.c.season_id == season_id)).first() is not None:
        return []
    return start_qualifying(conn, world, meta, season_id, today)


def progress_europe(conn: Connection, world: World, meta: CareerMeta, today: date) -> list[str]:
    """The day's European business: qualifying ties settled and the next rounds drawn, then the
    league phases and the knockouts."""
    if not enabled(world):
        return []
    messages = settle(conn, world, meta, today)
    return messages + _league_phase(conn, world, meta, today)


def _league_phase(conn: Connection, world: World, meta: CareerMeta, today: date) -> list[str]:
    """Draw the league phases once every qualifying round is decided (a club dropping from one
    competition's is in the next one's), and close each once its last matchday is played."""
    season_id = meta.season_id
    entries = conn.execute(select(continental_entry.c.id).where(
        continental_entry.c.season_id == season_id)).first()
    if entries is None:
        return []
    messages: list[str] = []
    drawn = {comp.key: conn.execute(select(fixture.c.id).where(
        fixture.c.season_id == season_id, fixture.c.stage == comp.key,
        fixture.c.round == 1)).first() is not None for comp in competitions_by_rank(world)}
    if not all(drawn.values()) and not qualifying_done(conn, world, season_id):
        return []
    for comp in competitions_by_rank(world):
        if not drawn[comp.key]:
            messages += draw_league_phase(conn, world, meta, comp, today)
            continue
        finished = conn.execute(select(continental_entry.c.id).where(
            continental_entry.c.season_id == season_id,
            continental_entry.c.competition_id == competition_id(conn, comp),
            continental_entry.c.position.is_not(None))).first()
        if finished is None and league_phase_done(conn, season_id, comp):
            rows = finish_league_phase(conn, world, meta, comp, today)
            messages += _phase_news(conn, meta, comp.name, comp.league_phase.to_playoff, rows)
        messages += progress_knockout(conn, world, meta, comp, today)
    return messages


def europe_decider(conn: Connection, world: World, fx: Row[Any]) -> Decider | None:
    """Knockout rules for a European fixture: none in the league phase or a first leg."""
    comp = world.defs.continental[fx.stage]
    if 1 <= fx.round < KNOCKOUT:
        return None  # a league-phase match: a draw stands
    legs = (qualifying_round(comp, fx.round).legs if fx.round <= QUALIFYING
            else comp.knockout[fx.round - KNOCKOUT].legs)
    if legs == 1:
        return Decider(extra_time=True, penalties=True)
    if fx.leg != 2:
        return None
    first = conn.execute(select(fixture).where(
        fixture.c.season_id == fx.season_id, fixture.c.stage == fx.stage,
        fixture.c.round == fx.round, fixture.c.tie == fx.tie, fixture.c.leg == 1)).one()
    prior = ((first.home_goals, first.away_goals) if first.home_club_id == fx.home_club_id
             else (first.away_goals, first.home_goals))
    return Decider(extra_time=True, penalties=True, first_leg=prior)


def _phase_news(conn: Connection, meta: CareerMeta, comp_name: str,
                playoff: tuple[int, int], rows: list[Any]) -> list[str]:
    user = meta.user_club_id
    row = next((r for r in rows if r.club_id == user), None)
    if user is None or row is None:
        return []
    then = ("into the round of 16" if row.position < playoff[0]
            else "into the knockout play-off" if row.position <= playoff[1] else "out")
    return [f"{club_name(conn, user)} finish {row.position} in the {comp_name} league phase "
            f"with {row.points} points: {then}."]
