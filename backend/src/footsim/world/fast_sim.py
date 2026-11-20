"""Which matches are fully simulated, and fast results for the rest (Settings → Simulation).

The user chooses which leagues are fully simulated (CareerMeta.fast_leagues lists those that
aren't; empty, the default, simulates everything as before). A fixture gets a fast result
(match/fast.py) when:
- it is a league match (or a league's play-off) of a league switched to fast, or a college match
  with the NCAA switched to fast;
- it is a domestic cup tie between two clubs whose leagues are both fast (a club outside any
  league counts as fast when every league of the cup's country is).
Continental competitions are always fully simulated, and so is the user's own league, whatever
the setting says. The user's own matches never come here.

Fast days are cheap in two ways besides the one draw per match:
- a club's team sheet is kept between its matches while nothing it depends on changes (its
  players, their condition and availability, its tactic, and the players' ratings by
  players_epoch), so the line-up isn't picked again every match;
- the day's fast results are written together, a few statements for all of them.
"""

from collections import defaultdict
from datetime import date
from typing import Any
from weakref import WeakKeyDictionary

from sqlalchemy import Connection, Engine, Row, text

from footsim.core.rng import derive_rng
from footsim.match.report import MatchReport
from footsim.match.teams import TeamSheet
from footsim.world.college.common import LOWER_TYPE
from footsim.world.context import World
from footsim.world.international.common import away_players, national_club_ids
from footsim.world.international.windows import FRIENDLY
from footsim.world.meta import CareerMeta, players_epoch
from footsim.world.news_scope import effective_fast, user_league
from footsim.world.season import decider_for
from footsim.world.squads import team_sheet

SIM = "fast"  # fixture.sim for a fast result


__all__ = ["effective_fast", "user_league"]  # moved to news_scope; kept importable here


# --- the setting -------------------------------------------------------------------------


def selectable(world: World) -> dict[str, str]:
    """The competitions the user can switch to fast, by key, with their country's code:
    every league, and the NCAA's college season."""
    found = {key: lg.nation for key, lg in world.defs.leagues.items()}
    found[world.defs.college.rules.key] = "USA"
    return found


def set_fast_leagues(world: World, meta: CareerMeta, keys: list[str]) -> None:
    known = selectable(world)
    unknown = sorted(set(keys) - set(known))
    if unknown:
        raise ValueError(f"unknown leagues: {', '.join(unknown)}")
    meta.fast_leagues = sorted(set(keys))


# --- which fixtures are fast -------------------------------------------------------------


def split_day(conn: Connection, world: World, meta: CareerMeta, games: list[Row[Any]]
              ) -> tuple[list[Row[Any]], list[Row[Any]]]:
    """The day's AI fixtures as (fully simulated, fast), each in fixture-id order."""
    fast = effective_fast(conn, meta) if meta.fast_leagues else set()
    if not games:
        return games, []
    comps = {int(r.id): (str(r.key), str(r.type))
             for r in conn.execute(text("SELECT id, key, type FROM competition"))}
    # International friendlies always get fast results, unless the user's national team plays.
    friendly = {cid for cid, (key, _) in comps.items() if key == FRIENDLY}
    if not fast and not any(fx.competition_id in friendly for fx in games):
        return games, []
    leagues: dict[int, str] | None = None
    real: list[Row[Any]] = []
    quick: list[Row[Any]] = []
    for fx in games:
        key, kind = comps[fx.competition_id]
        if key == FRIENDLY:
            is_fast = meta.user_nation_id not in (fx.home_club_id, fx.away_club_id)
        elif kind == LOWER_TYPE:  # D-II and D-III: always quick results (W9e)
            is_fast = True
        elif kind in ("league", "college"):
            is_fast = key in fast
        elif kind == "cup" and key in world.defs.cups:
            if leagues is None:
                leagues = {int(r.club_id): str(r.key) for r in conn.execute(text(
                    "SELECT m.club_id, c.key FROM club_league_membership m "
                    "JOIN competition c ON c.id = m.competition_id WHERE m.season_id = :s"),
                    {"s": meta.season_id})}
            nation = world.defs.cups[key].nation
            homeless = all(k in fast for k, lg in world.defs.leagues.items()
                           if lg.nation == nation)
            is_fast = all((leagues[c] in fast) if c in leagues else homeless
                          for c in (fx.home_club_id, fx.away_club_id))
        else:  # continental, and anything else: always fully simulated
            is_fast = False
        (quick if is_fast else real).append(fx)
    return real, quick


# --- team sheets kept between matches ----------------------------------------------------

# Each open database's kept sheets, by club: (what the sheet was built from, the sheet). The key
# holds everything team_sheet reads that can change (the club's players and their condition
# and availability, its tactic, and players_epoch for ratings and positions), so a kept sheet
# is exactly the one team_sheet would build now. Dropped with the database's market cache when a
# write rolls back (api/session.py).
_SHEETS: WeakKeyDictionary[Engine, dict[int, tuple[tuple[Any, ...], TeamSheet]]] = (
    WeakKeyDictionary())


def forget_sheets(engine: Engine) -> None:
    _SHEETS.pop(engine, None)


def _sheet_keys(conn: Connection, clubs: list[int], day: date) -> dict[int, tuple[Any, ...]]:
    params = {f"c{k}": c for k, c in enumerate(clubs)}
    marks = ", ".join(f":{k}" for k in params)
    members: dict[int, list[tuple[Any, ...]]] = defaultdict(list)
    away = away_players(conn, day)
    national = national_club_ids(conn)
    for r in conn.execute(text(f"""
            SELECT k.club_id, k.person_id, s.condition, s.injured_until, s.suspended_matches
            FROM (SELECT club_id, person_id FROM playing
                  UNION ALL SELECT club_id, player_id FROM national_squad
                  UNION ALL SELECT club_id, player_id FROM guest_player) k
            LEFT JOIN player_state s ON s.player_id = k.person_id
            WHERE k.club_id IN ({marks}) ORDER BY k.club_id, k.person_id"""), params):
        injured = r.injured_until is not None and date.fromisoformat(r.injured_until) > day
        gone = r.club_id not in national and r.person_id in away
        members[r.club_id].append((r.person_id, r.condition,
                                   not injured and not (r.suspended_matches or 0) and not gone))
    tactics = {r.club_id: tuple(r) for r in conn.execute(text(
        f"SELECT club_id, formation, roles, lineup, instructions FROM tactic "
        f"WHERE club_id IN ({marks})"), params)}
    epoch = players_epoch(conn)
    return {c: (epoch, tactics.get(c), tuple(members[c])) for c in clubs}


def _sheets(conn: Connection, world: World, clubs: list[int], day: date) -> dict[int, TeamSheet]:
    kept = _SHEETS.setdefault(conn.engine, {})
    keys = _sheet_keys(conn, clubs, day)
    sheets = {}
    for club_id in clubs:
        entry = kept.get(club_id)
        if entry is None or entry[0] != keys[club_id]:
            entry = (keys[club_id], team_sheet(conn, world, club_id, day))
            kept[club_id] = entry
        sheets[club_id] = entry[1]
    return sheets


# --- playing and recording a fast day ----------------------------------------------------


def play_fast(conn: Connection, world: World, meta: CareerMeta, games: list[Row[Any]],
              day: date) -> list[MatchReport]:
    """Fast results for ``games`` (one day's, in fixture-id order), written together."""
    if not games:
        return []
    clubs = sorted({c for fx in games for c in (fx.home_club_id, fx.away_club_id)})
    sheets = _sheets(conn, world, clubs, day)
    reports = []
    for fx in games:
        rng = derive_rng(meta.seed, "fast-match", fx.id)
        reports.append(world.fast.play(sheets[fx.home_club_id], sheets[fx.away_club_id], rng,
                                       neutral=bool(fx.neutral),
                                       decider=decider_for(conn, world, fx)))
    _record(conn, world, [fx.id for fx in games], reports)
    return reports


def _record(conn: Connection, world: World, fixture_ids: list[int],
            reports: list[MatchReport]) -> None:
    """Every fast result of the day: the fixtures (no match statistics), goals and substitutions,
    the players' lines (minutes, goals, assists and ratings),
    bans served, and the unused substitutes' development credit (as results.record_result)."""
    conn.execute(text("""
        UPDATE fixture SET status = 'played', home_goals = :hg, away_goals = :ag,
            extra_time = :et, home_pens = :hp, away_pens = :ap, sim = :sim, stats = NULL
        WHERE id = :id"""), [  # no match statistics: the score, events and lines are all
        {"id": fid, "hg": r.home_goals, "ag": r.away_goals, "et": int(r.extra_time),
         "hp": r.home_pens, "ap": r.away_pens, "sim": SIM}
        for fid, r in zip(fixture_ids, reports, strict=True)])
    events = [(fid, e.minute, e.type, e.club_id, e.player_id, e.other_player_id, e.detail)
              for fid, r in zip(fixture_ids, reports, strict=True) for e in r.events]
    if events:
        conn.exec_driver_sql(
            "INSERT INTO match_event (fixture_id, minute, type, club_id, player_id, "
            "other_player_id, detail) VALUES (?, ?, ?, ?, ?, ?, ?)", events)
    lines = [(fid, ln.player_id, ln.club_id, int(ln.started), ln.minutes, ln.goals, ln.assists,
              ln.rating)
             for fid, r in zip(fixture_ids, reports, strict=True) for ln in r.players.values()]
    if lines:
        conn.exec_driver_sql(
            "INSERT INTO player_match (fixture_id, player_id, club_id, started, minutes, goals, "
            "assists, shots, shots_on_target, passes, passes_completed, tackles, "
            "interceptions, saves, yellow, red, rating) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, ?)", lines)
    # A ban is served by any match the club plays (as results.record_result).
    clubs = [c for r in reports for c in (r.home_club_id, r.away_club_id)]
    marks = ", ".join("?" for _ in clubs)
    conn.exec_driver_sql(
        "UPDATE player_state SET suspended_matches = suspended_matches - 1 "
        f"WHERE suspended_matches > 0 AND player_id IN (SELECT person_id FROM playing "
        f"WHERE club_id IN ({marks}))", tuple(clubs))
    unused = [pid for r in reports for pid in r.bench if pid not in r.players]
    if unused:
        credit = world.defs.development.bench_credit_minutes
        conn.exec_driver_sql(
            "UPDATE player_state SET bench_minutes = bench_minutes + ? WHERE player_id = ?",
            [(credit, pid) for pid in unused])
