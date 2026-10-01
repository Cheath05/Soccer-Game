"""Career flow: starting a career, advancing the calendar, playing fixtures."""

import json
import secrets
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Connection, Row, func, literal, or_, select, text

from footsim.core.rng import derive_rng
from footsim.match.engine.engine import MatchEngine
from footsim.match.report import MatchReport
from footsim.persistence.schema import fixture, game_meta, metadata, player, player_state
from footsim.world.context import World
from footsim.world.meta import CareerMeta, read_meta, write_meta
from footsim.world.results import daily_recovery, record_result
from footsim.world.season import (
    after_day,
    create_season_fixtures,
    decider_for,
    refresh_ai_tactics,
    rollover,
    season_calendar,
    season_complete,
)
from footsim.world.squads import team_sheet

MAX_ADVANCE_DAYS = 400


@dataclass
class AdvanceResult:
    date: date
    stop: str  # match | season_end | limit
    fixture_id: int | None = None
    messages: list[str] = field(default_factory=list)


def initialize_career(conn: Connection, world: World, club_id: int | None,
                      manager_name: str | None, seed: int | None = None) -> None:
    """Turn a freshly cloned base world into a career for ``club_id`` (None: watch only).

    Each career gets its own random seed (unless one is given), so two careers from the
    same world play out differently; within a career everything stays reproducible."""
    metadata.create_all(conn)  # worlds built before a schema addition get the new tables
    base = {k: json.loads(v) for k, v in conn.execute(select(game_meta.c.key, game_meta.c.value))}
    calendar_key = base["calendar"]
    start = world.defs.calendars[calendar_key].season_start
    career_seed = seed if seed is not None else secrets.randbits(31)
    meta = CareerMeta(world_seed=career_seed, current_date=start, season_id=1,
                      base_calendar=calendar_key, user_club_id=club_id,
                      manager_name=manager_name)
    write_meta(conn, meta)
    conn.execute(player_state.insert().from_select(
        ["player_id", "condition", "form", "suspended_matches", "season_yellows"],
        select(player.c.person_id, literal(100.0), literal(6.5), literal(0), literal(0)),
    ))
    refresh_ai_tactics(conn, world, meta, start)
    create_season_fixtures(conn, world, meta, 1)


def _user_fixture(conn: Connection, meta: CareerMeta, day: date) -> Row[Any] | None:
    if meta.user_club_id is None:
        return None
    return conn.execute(select(fixture).where(
        fixture.c.date == day.isoformat(), fixture.c.status == "scheduled",
        or_(fixture.c.home_club_id == meta.user_club_id,
            fixture.c.away_club_id == meta.user_club_id),
    )).first()


def next_user_fixture(conn: Connection, meta: CareerMeta) -> Row[Any] | None:
    if meta.user_club_id is None:
        return None
    return conn.execute(select(fixture).where(
        fixture.c.status == "scheduled",
        or_(fixture.c.home_club_id == meta.user_club_id,
            fixture.c.away_club_id == meta.user_club_id),
    ).order_by(fixture.c.date)).first()


def play_fixture(conn: Connection, world: World, meta: CareerMeta, fx: Row[Any], day: date,
                 sim: str = "quick") -> MatchReport:
    home = team_sheet(conn, world, fx.home_club_id, day)
    away = team_sheet(conn, world, fx.away_club_id, day)
    rng = derive_rng(meta.seed, "match", fx.id)
    report = world.quick.play(home, away, rng, neutral=bool(fx.neutral),
                              decider=decider_for(conn, world, fx))
    record_result(conn, fx.id, report, day, sim)
    return report


def agent_match(conn: Connection, world: World, meta: CareerMeta, fx: Row[Any], day: date,
                record: bool) -> MatchEngine:
    """The watchable agent-based engine, set up for fixture ``fx``."""
    home = team_sheet(conn, world, fx.home_club_id, day)
    away = team_sheet(conn, world, fx.away_club_id, day)
    rng = derive_rng(meta.seed, "live-match", fx.id)
    # Computer-controlled sides adjust their tactics during the match; the user's side is
    # the user's to manage (he can hand it to the assistant while watching).
    ai_manager = (fx.home_club_id != meta.user_club_id, fx.away_club_id != meta.user_club_id)
    return MatchEngine(world.defs, home, away, rng, neutral=bool(fx.neutral),
                       decider=decider_for(conn, world, fx), record=record,
                       ai_manager=ai_manager)


def play_user_instant(conn: Connection, world: World, meta: CareerMeta, fx: Row[Any],
                      day: date) -> MatchReport:
    """The user's match without watching: the same agent engine, run headless."""
    engine = agent_match(conn, world, meta, fx, day, record=False)
    engine.run()
    report = engine.report()
    record_result(conn, fx.id, report, day, "instant")
    return report


def _play_day(conn: Connection, world: World, meta: CareerMeta, day: date) -> None:
    games = conn.execute(select(fixture).where(
        fixture.c.date == day.isoformat(), fixture.c.status == "scheduled",
    ).order_by(fixture.c.id)).all()
    for fx in games:
        if meta.user_club_id in (fx.home_club_id, fx.away_club_id):
            continue
        play_fixture(conn, world, meta, fx, day)


def advance(conn: Connection, world: World, max_days: int = MAX_ADVANCE_DAYS) -> AdvanceResult:
    """Simulate day by day until the user's next match day or the end of the season."""
    meta = read_meta(conn)
    day = meta.current_date
    messages: list[str] = []
    for _ in range(max_days):
        _play_day(conn, world, meta, day)
        user_fx = _user_fixture(conn, meta, day)
        if user_fx is not None:
            meta.current_date = day
            write_meta(conn, meta)
            return AdvanceResult(day, "match", user_fx.id, messages)
        messages += after_day(conn, world, meta, day)
        calendar = season_calendar(world, meta, meta.season_id)
        if day >= calendar.season_end and season_complete(conn, meta.season_id):
            messages += rollover(conn, world, meta)
            day += timedelta(days=1)
            daily_recovery(conn, day)
            meta.current_date = day
            write_meta(conn, meta)
            return AdvanceResult(day, "season_end", None, messages)
        day += timedelta(days=1)
        daily_recovery(conn, day)
        meta.current_date = day
        write_meta(conn, meta)
    return AdvanceResult(day, "limit", None, messages)


@dataclass
class SimStep:
    """One step of simulating towards a date (``sim_step``)."""

    date: date
    stop: str | None  # why it ends here: "date" or "season_end"; None to carry on
    fixture_id: int | None = None  # the user's match played in this step
    messages: list[str] = field(default_factory=list)


def sim_step(conn: Connection, world: World, until: date) -> SimStep:
    """Move the career towards ``until`` (sim to date): play the user's match today as Instant
    would, if there is one, or else advance to his next match day or to ``until``, whichever
    comes first. Days before ``until`` are played; ``until`` itself is left to the user, so a
    match on that day can still be watched. The season's end also stops it."""
    meta = read_meta(conn)
    day = meta.current_date
    if day >= until:
        return SimStep(day, "date")
    user_fx = _user_fixture(conn, meta, day)
    if user_fx is not None:
        play_user_instant(conn, world, meta, user_fx, day)
        return SimStep(day, None, user_fx.id)
    result = advance(conn, world, max_days=(until - day).days)
    stop = {"match": None, "season_end": "season_end"}.get(result.stop, "date")
    return SimStep(result.date, stop, messages=result.messages)


def set_user_tactic(conn: Connection, world: World, formation: str, roles: dict[str, str],
                    lineup: dict[str, int] | None, instructions: dict[str, str]) -> None:
    meta = read_meta(conn)
    if formation not in world.defs.formations:
        raise ValueError(f"unknown formation {formation}")
    for slot, role in roles.items():
        if role not in world.defs.roles:
            raise ValueError(f"unknown role {role} for slot {slot}")
    conn.execute(text("""
        INSERT INTO tactic (club_id, formation, roles, lineup, instructions)
        VALUES (:club, :formation, :roles, :lineup, :instructions)
        ON CONFLICT(club_id) DO UPDATE SET formation = excluded.formation,
            roles = excluded.roles, lineup = excluded.lineup, instructions = excluded.instructions
    """), {"club": meta.user_club_id, "formation": formation, "roles": json.dumps(roles),
           "lineup": json.dumps(lineup) if lineup else None,
           "instructions": json.dumps(instructions)})


def scheduled_count(conn: Connection, season_id: int) -> int:
    return int(conn.execute(select(func.count()).select_from(fixture).where(
        fixture.c.season_id == season_id, fixture.c.status == "scheduled")).scalar_one())
