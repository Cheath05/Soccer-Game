"""Writes a finished match into the save: result, events, player stats, fitness, form,
injuries, suspensions and the development credit for unused substitutes."""

import json
from dataclasses import asdict
from datetime import date, timedelta

from sqlalchemy import Connection, select, text, update

from footsim.match.report import RED_DOGSO, RED_SECOND_YELLOW, MatchReport
from footsim.persistence.schema import fixture, match_event, player_match, player_state
from footsim.world.context import get_world

YELLOWS_FOR_BAN = 5
SECOND_YELLOW_BAN = 1
DOGSO_BAN = 1  # a red card for denying an obvious goal-scoring chance (the FA's one match)
STRAIGHT_RED_BAN = 3
FORM_WEIGHT = 0.3  # weight of the latest match in the rolling form rating


def record_result(conn: Connection, fixture_id: int, report: MatchReport, day: date,
                  sim: str) -> None:
    conn.execute(update(fixture).where(fixture.c.id == fixture_id).values(
        status="played", home_goals=report.home_goals, away_goals=report.away_goals,
        extra_time=int(report.extra_time), home_pens=report.home_pens,
        away_pens=report.away_pens, sim=sim,
        stats=json.dumps({"home": asdict(report.home_stats), "away": asdict(report.away_stats)}),
    ))
    if report.events:
        conn.execute(match_event.insert(), [
            {"fixture_id": fixture_id, "minute": e.minute, "type": e.type, "club_id": e.club_id,
             "player_id": e.player_id, "other_player_id": e.other_player_id, "detail": e.detail,
             "period": e.period, "second": e.second}
            for e in report.events
        ])
    lines = list(report.players.values())
    if lines:
        conn.execute(player_match.insert(), [
            {"fixture_id": fixture_id, "player_id": ln.player_id, "club_id": ln.club_id,
             "started": int(ln.started), "minutes": ln.minutes, "goals": ln.goals,
             "assists": ln.assists, "shots": ln.shots, "shots_on_target": ln.shots_on_target,
             "passes": ln.passes, "passes_completed": ln.passes_completed,
             "tackles": ln.tackles, "interceptions": ln.interceptions, "saves": ln.saves,
             "yellow": ln.yellow, "red": ln.red, "rating": ln.rating}
            for ln in lines
        ])
    credit_bench(conn, report)

    # Suspended players can't play, so every club member with a ban has now served a game.
    # (Bans picked up in this match are added below, after this decrement.)
    for club_id in (report.home_club_id, report.away_club_id):
        conn.execute(text("""
            UPDATE player_state SET suspended_matches = suspended_matches - 1
            WHERE suspended_matches > 0 AND player_id IN (
                SELECT person_id FROM playing WHERE club_id = :club)
        """), {"club": club_id})

    states = {r.player_id: r for r in conn.execute(
        select(player_state).where(player_state.c.player_id.in_([ln.player_id for ln in lines]))
    )}
    reds = {e.player_id: e.detail for e in report.events if e.type == "red"}
    for ln in lines:
        state = states.get(ln.player_id)
        if state is None:
            continue
        season_yellows = state.season_yellows + ln.yellow
        ban = state.suspended_matches
        if ln.red:
            reason = reds.get(ln.player_id)
            ban += (SECOND_YELLOW_BAN if reason == RED_SECOND_YELLOW else
                    DOGSO_BAN if reason == RED_DOGSO else STRAIGHT_RED_BAN)
        elif ln.yellow and season_yellows % YELLOWS_FOR_BAN == 0:
            ban += 1
        conn.execute(update(player_state).where(player_state.c.player_id == ln.player_id).values(
            condition=min(state.condition, report.fitness.get(ln.player_id, state.condition)),
            form=round((1 - FORM_WEIGHT) * state.form + FORM_WEIGHT * ln.rating, 2),
            season_yellows=season_yellows,
            suspended_matches=ban,
        ))
    for injury in report.injuries:
        conn.execute(update(player_state).where(player_state.c.player_id == injury.player_id)
                     .values(injured_until=(day + timedelta(days=injury.days)).isoformat(),
                             injury=injury.name))


def credit_bench(conn: Connection, report: MatchReport) -> None:
    """Every substitute named for the match who never came on is credited a few development
    minutes (development.yaml bench_credit_minutes): he trained and travelled with the first
    team. It's a running total on his player_state row that fades each month, when development
    runs (world/season.py develop_players). Both engines name their bench in the report."""
    unused = [pid for pid in report.bench if pid not in report.players]
    if unused:
        credit = get_world().defs.development.bench_credit_minutes
        conn.execute(update(player_state).where(player_state.c.player_id.in_(unused))
                     .values(bench_minutes=player_state.c.bench_minutes + credit))


def daily_recovery(conn: Connection, day: date) -> None:
    """Condition recovers overnight (faster with better natural fitness); injuries heal."""
    conn.execute(text("""
        UPDATE player_state SET condition = MIN(100.0, condition + 7.0 + 6.0 * (
            SELECT natural_fitness FROM player_attr WHERE player_id = player_state.player_id
        ) / 100.0)
        WHERE condition < 100.0
    """))
    conn.execute(text("""
        UPDATE player_state SET injured_until = NULL, injury = NULL
        WHERE injured_until IS NOT NULL AND injured_until <= :day
    """), {"day": day.isoformat()})
