"""A European season's stages, as the days come: entries and the summer play-off draw when
the season starts, then the play-off round's results (winners into the league phase, losers
down into the next competition's). The league phase and the knockouts follow (W6 E3, E4).

Ties use the domestic cups' machinery: ``cup_tie`` rows, fixtures with ``leg`` 1 and 2, the
Decider for extra time and penalties, and moving a club's league matches out of the way."""

from datetime import date
from typing import Any

from sqlalchemy import Connection, Row, delete, select, update

from footsim.core.rng import derive_rng
from footsim.match.report import Decider
from footsim.persistence.schema import club, continental_entry, cup_tie, fixture, nation
from footsim.world.context import World
from footsim.world.europe.access import qualify
from footsim.world.europe.coefficients import coefficients
from footsim.world.europe.common import (
    KNOCKOUT,
    QUALIFYING,
    competition_id,
    competitions_by_rank,
    enabled,
    europe_calendar,
)
from footsim.world.europe.knockout import progress_knockout
from footsim.world.europe.league_phase import (
    draw_league_phase,
    finish_league_phase,
    league_phase_done,
)
from footsim.world.europe.ties import insert_ties, tie_winner
from footsim.world.meta import CareerMeta
from footsim.world.squads import club_name

DRAW_TRIES = 200  # reshuffles of a draw looking for one without two clubs of a country


def start_europe(conn: Connection, world: World, meta: CareerMeta, season_id: int,
                 today: date) -> list[str]:
    """The season's European entries, and the summer play-off draws with their fixtures.
    Nothing when the European competitions are switched off, or already started."""
    if not enabled(world) or conn.execute(select(continental_entry.c.id).where(
            continental_entry.c.season_id == season_id)).first() is not None:
        return []
    entries = qualify(conn, world, meta, season_id)
    ids = {comp.key: competition_id(conn, comp) for comp in competitions_by_rank(world)}
    if entries:
        conn.execute(continental_entry.insert(), [
            {"season_id": season_id, "competition_id": ids[e.competition], "club_id": e.club_id,
             "stage": e.stage, "route": e.route, "pot": None, "position": None}
            for e in entries])
    messages = _entry_news(conn, world, meta, entries)
    calendar = europe_calendar(world, season_id)
    for comp in competitions_by_rank(world):
        clubs = [e.club_id for e in entries
                 if e.competition == comp.key and e.stage == "qualifying"]
        if not clubs:
            continue
        ties = _seeded_draw(conn, world, meta, season_id, comp.key, clubs)
        days = calendar.competitions[comp.key].qualifying
        insert_ties(conn, world, season_id, ids[comp.key], comp.key, QUALIFYING, ties, days,
                     neutral=False, today=today)
        messages += _draw_news(conn, meta, comp.name, comp.qualifying.name, ties, days)
    return messages


def _seeded_draw(conn: Connection, world: World, meta: CareerMeta, season_id: int,
                 comp_key: str, clubs: list[int]) -> list[tuple[int, int]]:
    """Pairs for a two-legged round: the higher half by coefficient seeded, each drawn against
    an unseeded club, avoiding two clubs of one country where a draw allows. The unseeded club
    is at home first, the seeded club in the second leg."""
    coeff = coefficients(conn, world, clubs, season_id)
    ranked = sorted(clubs, key=lambda c: (-coeff[c], c))
    half = len(ranked) // 2
    seeded, unseeded = ranked[:half], ranked[half:]
    country = {r.id: r.code for r in conn.execute(
        select(club.c.id, nation.c.code).join(nation, nation.c.id == club.c.nation_id)
        .where(club.c.id.in_(clubs)))}
    rng = derive_rng(meta.seed, "europe-draw", season_id, comp_key, QUALIFYING)
    best: list[int] = list(unseeded)
    for _ in range(DRAW_TRIES):
        order = [unseeded[k] for k in rng.permutation(len(unseeded))]
        best = order
        if all(country.get(a) != country.get(b) for a, b in zip(order, seeded, strict=True)):
            break
    return list(zip(best, seeded, strict=True))


def progress_europe(conn: Connection, world: World, meta: CareerMeta, today: date) -> list[str]:
    """Settle the European ties played so far: a summer play-off round's winners go into the
    league phase, its losers into the next competition's or out."""
    if not enabled(world):
        return []
    messages: list[str] = []
    for comp in competitions_by_rank(world):
        comp_id = competition_id(conn, comp)
        open_ties = conn.execute(select(cup_tie).where(
            cup_tie.c.season_id == meta.season_id, cup_tie.c.competition_id == comp_id,
            cup_tie.c.round == QUALIFYING, cup_tie.c.winner_club_id.is_(None))).all()
        for tie in open_ties:
            winner = tie_winner(conn, meta.season_id, comp.key, tie)
            if winner is None:
                continue
            loser = tie.club_b_id if winner == tie.club_a_id else tie.club_a_id
            conn.execute(update(cup_tie).where(cup_tie.c.id == tie.id)
                         .values(winner_club_id=winner))
            conn.execute(update(continental_entry).where(
                continental_entry.c.season_id == meta.season_id,
                continental_entry.c.club_id == winner).values(stage="league_phase"))
            drop = comp.qualifying.losers_to
            if drop is not None:
                conn.execute(update(continental_entry).where(
                    continental_entry.c.season_id == meta.season_id,
                    continental_entry.c.club_id == loser).values(
                    competition_id=competition_id(conn, world.defs.continental[drop]),
                    stage="league_phase", route=f"dropped:{comp.key}"))
            else:
                conn.execute(delete(continental_entry).where(
                    continental_entry.c.season_id == meta.season_id,
                    continental_entry.c.club_id == loser))
            messages += _result_news(conn, world, meta, comp.key, winner, loser)
    messages += _league_phase(conn, world, meta, today)
    return messages


def _league_phase(conn: Connection, world: World, meta: CareerMeta, today: date) -> list[str]:
    """Draw the league phases once every play-off round is decided (a club dropping from one
    competition's is in the next one's), and close each once its last matchday is played."""
    season_id = meta.season_id
    entries = conn.execute(select(continental_entry.c.id).where(
        continental_entry.c.season_id == season_id)).first()
    if entries is None:
        return []
    undecided = conn.execute(select(cup_tie.c.id).where(
        cup_tie.c.season_id == season_id, cup_tie.c.round == QUALIFYING,
        cup_tie.c.winner_club_id.is_(None),
        cup_tie.c.competition_id.in_([competition_id(conn, c)
                                      for c in competitions_by_rank(world)]))).first()
    if undecided is not None:
        return []
    messages: list[str] = []
    for comp in competitions_by_rank(world):
        drawn = conn.execute(select(fixture.c.id).where(
            fixture.c.season_id == season_id, fixture.c.stage == comp.key,
            fixture.c.round == 1)).first()
        if drawn is None:
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
    legs = comp.qualifying.legs if fx.round == QUALIFYING else comp.knockout[
        fx.round - KNOCKOUT].legs
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


# --- news -------------------------------------------------------------------------------------

def _entry_news(conn: Connection, world: World, meta: CareerMeta,
                entries: list[Any]) -> list[str]:
    user = meta.user_club_id
    mine = next((e for e in entries if e.club_id == user), None)
    if mine is None or user is None:
        return []
    comp = world.defs.continental[mine.competition]
    where = ("the league phase" if mine.stage == "league_phase"
             else f"the {comp.qualifying.name.lower()}")
    return [f"{club_name(conn, user)} are in the {comp.name}: {where}."]


def _draw_news(conn: Connection, meta: CareerMeta, comp_name: str, round_name: str,
               ties: list[tuple[int, int]], days: list[list[date]]) -> list[str]:
    user = meta.user_club_id
    for n, (a, b) in enumerate(ties, start=1):
        if user in (a, b):
            when = " and ".join(f"{d:%a} {d.day} {d:%b}" for d in
                                (leg[(n - 1) % len(leg)] for leg in days))
            return [f"{comp_name} {round_name.lower()} draw: {club_name(conn, a)} v "
                    f"{club_name(conn, b)} ({when})."]
    return []


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


def _result_news(conn: Connection, world: World, meta: CareerMeta, comp_key: str,
                 winner: int, loser: int) -> list[str]:
    user = meta.user_club_id
    comp = world.defs.continental[comp_key]
    if user == winner:
        return [f"{club_name(conn, user)} are through to the {comp.name} league phase."]
    if user == loser:
        drop = comp.qualifying.losers_to
        then = (f" They go into the {world.defs.continental[drop].name} league phase."
                if drop else "")
        return [f"{club_name(conn, user)} are out of the {comp.name}, beaten by "
                f"{club_name(conn, winner)}.{then}"]
    return []
