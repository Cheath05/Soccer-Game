"""Season lifecycle: fixtures, final tables, play-offs, promotion/relegation, rollover."""

import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
from sqlalchemy import Connection, Row, func, select, text, update

from footsim.competitions.calendars import shifted_calendar
from footsim.competitions.fixtures import round_robin
from footsim.competitions.playoffs import Entrant, legs_for, round_ties
from footsim.competitions.scheduling import league_round_dates, playoff_dates
from footsim.competitions.standings import Result, TableRow, league_table
from footsim.core.rng import derive_rng, derive_seed
from footsim.defs.calendar import SeasonCalendarDef
from footsim.defs.competitions import LeagueDef, MovementKind, PlayoffDef, SimLevel
from footsim.domain.attributes import ATTRIBUTES
from footsim.match.report import Decider
from footsim.people.development import DevelopmentInput, Traits, apply_month, draw_traits
from footsim.persistence.schema import (
    club_league_membership,
    competition,
    contract,
    fixture,
    league_final,
    player_attr,
    player_development,
    playoff_tie,
    season,
    tactic,
)
from footsim.world.context import AI_FORMATIONS, World, default_instructions
from footsim.world.cups import blocked_dates, cup_decider, progress_cups, start_cups
from footsim.world.meta import CareerMeta
from footsim.world.squads import club_name, display_name, load_squad

DEVELOPMENT_SHARE = 1 / 12  # of a year's development, applied on the first of each month


@dataclass(frozen=True)
class ActiveLeague:
    competition_id: int
    league: LeagueDef


def season_calendar(world: World, meta: CareerMeta, season_id: int) -> SeasonCalendarDef:
    return shifted_calendar(world.defs.calendars[meta.base_calendar], season_id - 1)


def active_leagues(conn: Connection, world: World) -> list[ActiveLeague]:
    rows = conn.execute(select(competition.c.id, competition.c.key)).all()
    result = []
    for row in rows:
        league = world.defs.leagues.get(row.key)
        if league is not None and league.sim_level is not SimLevel.DORMANT:
            result.append(ActiveLeague(row.id, league))
    return sorted(result, key=lambda a: (a.league.nation, a.league.tier))


def members(conn: Connection, season_id: int, competition_id: int) -> list[int]:
    rows = conn.execute(select(club_league_membership.c.club_id).where(
        club_league_membership.c.season_id == season_id,
        club_league_membership.c.competition_id == competition_id,
    ))
    return sorted(r.club_id for r in rows)


def create_season_fixtures(conn: Connection, world: World, meta: CareerMeta,
                           season_id: int) -> list[str]:
    """The season's league fixtures, around the cup rounds that keep leagues out, and the
    cups' first-round draws. Returns news of the draws."""
    calendar = season_calendar(world, meta, season_id)
    for active in active_leagues(conn, world):
        league = active.league
        clubs = members(conn, season_id, active.competition_id)
        rng = derive_rng(meta.seed, "fixtures", season_id, league.key)
        rounds = round_robin(clubs, league.format.legs, rng)
        dates = league_round_dates(calendar.competitions[league.key], calendar, len(rounds),
                                   blocked_dates(world, calendar, league.key))
        conn.execute(fixture.insert(), [
            {"season_id": season_id, "competition_id": active.competition_id, "stage": "league",
             "round": number, "date": day.isoformat(), "home_club_id": home,
             "away_club_id": away, "neutral": 0, "status": "scheduled"}
            for number, (games, day) in enumerate(zip(rounds, dates, strict=True), start=1)
            for home, away in games
        ])
    return start_cups(conn, world, meta, calendar, meta.current_date)


def league_results(conn: Connection, competition_id: int, season_id: int) -> list[Result]:
    rows = conn.execute(select(fixture).where(
        fixture.c.competition_id == competition_id, fixture.c.season_id == season_id,
        fixture.c.stage == "league", fixture.c.status == "played",
    ))
    return [Result(r.home_club_id, r.away_club_id, r.home_goals, r.away_goals) for r in rows]


def standings(conn: Connection, world: World, meta: CareerMeta, competition_id: int,
              season_id: int) -> list[TableRow]:
    key: str = conn.execute(select(competition.c.key).where(competition.c.id == competition_id)
                            ).scalar_one()
    league = world.defs.leagues[key]
    return league_table(members(conn, season_id, competition_id),
                        league_results(conn, competition_id, season_id), league.points,
                        league.tiebreakers, derive_seed(meta.seed, "lots", season_id, key))


def _scheduled(conn: Connection, competition_id: int, season_id: int, stage: str) -> int:
    return int(conn.execute(select(func.count()).select_from(fixture).where(
        fixture.c.competition_id == competition_id, fixture.c.season_id == season_id,
        fixture.c.stage == stage, fixture.c.status == "scheduled",
    )).scalar_one())


def _finalized(conn: Connection, competition_id: int, season_id: int) -> bool:
    return conn.execute(select(func.count()).select_from(league_final).where(
        league_final.c.competition_id == competition_id, league_final.c.season_id == season_id,
    )).scalar_one() > 0


def after_day(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """Close finished leagues, start and advance play-offs, and on the first of each month let
    players develop. Returns news messages."""
    messages: list[str] = []
    if day.day == 1:
        messages += develop_players(conn, world, meta, day, DEVELOPMENT_SHARE)
    messages += progress_cups(conn, world, meta, season_calendar(world, meta, meta.season_id),
                              day)
    for active in active_leagues(conn, world):
        cid, league = active.competition_id, active.league
        if not _finalized(conn, cid, meta.season_id):
            if _scheduled(conn, cid, meta.season_id, "league") == 0:
                messages += _finalize_league(conn, world, meta, cid, league)
            continue
        for playoff in league.playoffs:
            messages += _progress_playoff(conn, world, meta, cid, league, playoff)
    return messages


def _finalize_league(conn: Connection, world: World, meta: CareerMeta, competition_id: int,
                     league: LeagueDef) -> list[str]:
    table = standings(conn, world, meta, competition_id, meta.season_id)
    outcome: dict[int, str] = {}
    for mv in league.movements:
        label = "promoted" if mv.kind is MovementKind.PROMOTION else "relegated"
        for pos in range(mv.ranks[0], mv.ranks[1] + 1):
            outcome[pos] = label
    for playoff in league.playoffs:
        for pos in playoff.entrant_ranks():
            outcome[pos] = "playoffs"
    outcome[1] = "champion"
    conn.execute(league_final.insert(), [
        {"season_id": meta.season_id, "competition_id": competition_id, "club_id": row.club_id,
         "position": row.position, "played": row.played, "won": row.won, "drawn": row.drawn,
         "lost": row.lost, "goals_for": row.goals_for, "goals_against": row.goals_against,
         "points": row.points, "outcome": outcome.get(row.position)}
        for row in table
    ])
    champion = club_name(conn, table[0].club_id)
    messages = [f"{champion} are {league.name} champions."]
    ranks = {row.position: row.club_id for row in table}
    for playoff in league.playoffs:
        _create_playoff_round(conn, world, meta, competition_id, league, playoff, 0, ranks, {})
    return messages


def _create_playoff_round(conn: Connection, world: World, meta: CareerMeta, competition_id: int,
                          league: LeagueDef, playoff: PlayoffDef, round_index: int,
                          ranks: dict[int, int], winners: dict[str, Entrant]) -> None:
    calendar = season_calendar(world, meta, meta.season_id)
    dates_cfg = calendar.competitions[league.key]
    leg_dates = playoff_dates(dates_cfg.end, dates_cfg.playoffs_end, playoff.rounds)[round_index]
    rnd = playoff.rounds[round_index]
    for tie in round_ties(playoff, round_index, ranks, winners):
        conn.execute(playoff_tie.insert().values(
            season_id=meta.season_id, competition_id=competition_id, playoff_key=playoff.key,
            tie=tie.tie_id, round=round_index, club_a_id=tie.a.club_id, club_b_id=tie.b.club_id,
            rank_a=tie.a.rank, rank_b=tie.b.rank,
        ))
        for leg, day in zip(legs_for(tie, rnd), leg_dates, strict=True):
            conn.execute(fixture.insert().values(
                season_id=meta.season_id, competition_id=competition_id, stage=playoff.key,
                round=round_index, tie=tie.tie_id, leg=leg.leg, date=day.isoformat(),
                home_club_id=leg.home, away_club_id=leg.away, neutral=int(leg.neutral),
                status="scheduled",
            ))


def _tie_winner(conn: Connection, season_id: int, playoff_key: str, tie_id: str,
                club_a: int, club_b: int) -> int | None:
    games = conn.execute(select(fixture).where(
        fixture.c.season_id == season_id, fixture.c.stage == playoff_key, fixture.c.tie == tie_id,
    ).order_by(fixture.c.leg)).all()
    if not games or any(g.status != "played" for g in games):
        return None
    goals = {club_a: 0, club_b: 0}
    for g in games:
        goals[g.home_club_id] += g.home_goals
        goals[g.away_club_id] += g.away_goals
    if goals[club_a] != goals[club_b]:
        return club_a if goals[club_a] > goals[club_b] else club_b
    last = games[-1]
    if last.home_pens is None:
        return None
    winner: int = last.home_club_id if last.home_pens > last.away_pens else last.away_club_id
    return winner


def _progress_playoff(conn: Connection, world: World, meta: CareerMeta, competition_id: int,
                      league: LeagueDef, playoff: PlayoffDef) -> list[str]:
    ties = conn.execute(select(playoff_tie).where(
        playoff_tie.c.season_id == meta.season_id, playoff_tie.c.playoff_key == playoff.key,
    )).all()
    if not ties:
        return []
    for t in ties:
        if t.winner_club_id is None:
            winner = _tie_winner(conn, meta.season_id, playoff.key, t.tie, t.club_a_id,
                                 t.club_b_id)
            if winner is not None:
                conn.execute(update(playoff_tie).where(playoff_tie.c.id == t.id)
                             .values(winner_club_id=winner))
    ties = conn.execute(select(playoff_tie).where(
        playoff_tie.c.season_id == meta.season_id, playoff_tie.c.playoff_key == playoff.key,
    )).all()
    current = max(t.round for t in ties)
    in_round = [t for t in ties if t.round == current]
    if any(t.winner_club_id is None for t in in_round):
        return []
    if current + 1 < len(playoff.rounds):
        if any(t.round == current + 1 for t in ties):
            return []
        finals = conn.execute(select(league_final).where(
            league_final.c.season_id == meta.season_id,
            league_final.c.competition_id == competition_id,
        )).all()
        ranks = {r.position: r.club_id for r in finals}
        rank_of = {r.club_id: r.position for r in finals}
        winners = {t.tie: Entrant(t.winner_club_id, rank_of[t.winner_club_id]) for t in ties
                   if t.winner_club_id is not None}
        _create_playoff_round(conn, world, meta, competition_id, league, playoff, current + 1,
                              ranks, winners)
        return []
    champion = in_round[0].winner_club_id
    already: str | None = conn.execute(select(league_final.c.outcome).where(
        league_final.c.season_id == meta.season_id, league_final.c.club_id == champion,
        league_final.c.competition_id == competition_id,
    )).scalar_one()
    if already == "playoff_winner":
        return []
    conn.execute(update(league_final).where(
        league_final.c.season_id == meta.season_id, league_final.c.club_id == champion,
        league_final.c.competition_id == competition_id,
    ).values(outcome="playoff_winner"))
    return [f"{club_name(conn, champion)} win the {playoff.name}."]


def decider_for(conn: Connection, world: World, fx: Row[Any]) -> Decider | None:
    """Knockout rules for a play-off or cup fixture; None for league games and first legs."""
    if fx.stage == "league":
        return None
    if fx.stage in world.defs.cups:
        return cup_decider(conn, world, fx)
    comp_key: str = conn.execute(select(competition.c.key).where(
        competition.c.id == fx.competition_id)).scalar_one()
    playoff = next(p for p in world.defs.leagues[comp_key].playoffs if p.key == fx.stage)
    rnd = playoff.rounds[fx.round]
    if rnd.legs == 1:
        return Decider(extra_time=rnd.extra_time, penalties=rnd.penalties)
    if fx.leg != 2:
        return None
    first = conn.execute(select(fixture).where(
        fixture.c.season_id == fx.season_id, fixture.c.stage == fx.stage,
        fixture.c.tie == fx.tie, fixture.c.leg == 1,
    )).one()
    prior = ((first.home_goals, first.away_goals) if first.home_club_id == fx.home_club_id
             else (first.away_goals, first.home_goals))
    return Decider(extra_time=rnd.extra_time, penalties=rnd.penalties, first_leg=prior)


def season_complete(conn: Connection, season_id: int) -> bool:
    return conn.execute(select(func.count()).select_from(fixture).where(
        fixture.c.season_id == season_id, fixture.c.status == "scheduled",
    )).scalar_one() == 0


def rollover(conn: Connection, world: World, meta: CareerMeta) -> list[str]:
    """Start the next season: promotion/relegation, development, contracts, fixtures."""
    old, new = meta.season_id, meta.season_id + 1
    calendar = season_calendar(world, meta, new)
    conn.execute(season.insert().values(id=new, label=calendar.season,
                                        start_date=calendar.season_start.isoformat(),
                                        end_date=calendar.season_end.isoformat()))
    comp_id = {r.key: r.id for r in conn.execute(select(competition.c.id, competition.c.key))}
    messages: list[str] = []
    moves: dict[int, int] = {}
    for active in active_leagues(conn, world):
        league = active.league
        finals = conn.execute(select(league_final).where(
            league_final.c.season_id == old,
            league_final.c.competition_id == active.competition_id,
        )).all()
        by_pos = {r.position: r.club_id for r in finals}
        for mv in league.movements:
            for pos in range(mv.ranks[0], mv.ranks[1] + 1):
                moves[by_pos[pos]] = comp_id[mv.to]
        for playoff in league.playoffs:
            winner = next((r.club_id for r in finals if r.outcome == "playoff_winner"), None)
            if winner is not None and playoff.winner_to:
                moves[winner] = comp_id[playoff.winner_to]
    current = conn.execute(select(club_league_membership).where(
        club_league_membership.c.season_id == old)).all()
    new_rows = [{"club_id": r.club_id, "season_id": new,
                 "competition_id": moves.get(r.club_id, r.competition_id)} for r in current]
    counts: dict[int, int] = defaultdict(int)
    for row in new_rows:
        counts[row["competition_id"]] += 1
    for active in active_leagues(conn, world):
        if counts[active.competition_id] != active.league.clubs:
            raise RuntimeError(f"{active.league.key} would have {counts[active.competition_id]} "
                               f"clubs next season, expected {active.league.clubs}")
    conn.execute(club_league_membership.insert(), new_rows)
    key_of = {cid: key for key, cid in comp_id.items()}
    previous = {r.club_id: r.competition_id for r in current}
    for club_id, target in sorted(moves.items()):
        new_league = world.defs.leagues[key_of[target]]
        old_league = world.defs.leagues[key_of[previous[club_id]]]
        verb = "promoted to" if new_league.tier < old_league.tier else "relegated to"
        messages.append(f"{club_name(conn, club_id)} {verb} the {new_league.name}.")

    _renew_contracts(conn, meta, calendar.season_start, calendar.season_end)
    conn.execute(text("UPDATE player_state SET season_yellows = 0"))
    meta.season_id = new
    refresh_ai_tactics(conn, world, meta, calendar.season_start)
    messages += create_season_fixtures(conn, world, meta, new)
    messages.insert(0, f"The {calendar.season} season begins.")
    return messages


def develop_players(conn: Connection, world: World, meta: CareerMeta, day: date,
                    share: float) -> list[str]:
    """A month of development for every player (people/development.py): the young grow
    towards their ceilings, faster with minutes played in the past twelve months, and the old
    decline. Traits are drawn the first time a player needs them. Returns news of the user's
    players whose overall moved. ``share`` is kept for callers; a step is always a month."""
    rows = conn.execute(text("""
        SELECT p.id, p.first_name, p.last_name, p.known_as, p.birth_date, pl.pa_hidden,
               (SELECT position FROM player_position pp WHERE pp.player_id = p.id
                ORDER BY familiarity DESC LIMIT 1) AS position,
               COALESCE((SELECT SUM(minutes) FROM player_match pm JOIN fixture f
                         ON f.id = pm.fixture_id WHERE pm.player_id = p.id
                         AND f.date > :since AND f.date <= :day), 0) AS minutes
        FROM person p JOIN player pl ON pl.person_id = p.id
        ORDER BY p.id
    """), {"since": (day - timedelta(days=365)).isoformat(), "day": day.isoformat()}).all()
    attrs_rows = {r.player_id: r for r in conn.execute(select(player_attr))}
    ids = [r.id for r in rows]
    matrix = np.array([[getattr(attrs_rows[i], a) for a in ATTRIBUTES] for i in ids], dtype=float)
    groups = [world.defs.positions[r.position or "CM"].group for r in rows]
    potential = np.array([r.pa_hidden for r in rows], dtype=float)
    traits, progress, trend = _development_state(conn, world, meta, day, ids, potential)
    inp = DevelopmentInput(
        attrs=matrix,
        ages=np.array([(day - date.fromisoformat(r.birth_date)).days / 365.25 for r in rows]),
        potential=potential,
        groups=groups,
        minutes=np.array([r.minutes for r in rows], dtype=float),
    )
    new, progress, moves = apply_month(world.defs.development, world.model, inp, traits,
                                       progress, derive_rng(meta.seed, "development",
                                                            day.isoformat()))
    rules = world.defs.development
    moved = _own_overalls(world, new, groups) - _own_overalls(world, matrix, groups)
    trend = rules.trend_memory * trend + (1 - rules.trend_memory) * moved
    changed = np.any(new != matrix, axis=1)
    params = [{"pid": ids[i], **{a: int(new[i, j]) for j, a in enumerate(ATTRIBUTES)}}
              for i in np.flatnonzero(changed)]
    if params:
        assignments = ", ".join(f"{a} = :{a}" for a in ATTRIBUTES)
        conn.execute(text(f"UPDATE player_attr SET {assignments} WHERE player_id = :pid"), params)
    conn.execute(text("UPDATE player_development SET progress = :progress, trend = :trend "
                      "WHERE player_id = :pid"),
                 [{"pid": pid, "progress": float(p), "trend": float(t)}
                  for pid, p, t in zip(ids, progress, trend, strict=True)])
    return _development_news(conn, world, meta, rows, groups, matrix, new, moves)


def _own_overalls(world: World, attrs: np.ndarray, groups: list[Any]) -> np.ndarray:
    """Each player's overall in his own position group."""
    overalls = world.model.group_overalls(attrs)
    return np.array([overalls[g][i] for i, g in enumerate(groups)])


def _development_state(conn: Connection, world: World, meta: CareerMeta, day: date,
                       ids: list[int], potential: np.ndarray
                       ) -> tuple[Traits, np.ndarray, np.ndarray]:
    """Every player's traits, progress and trend, drawing traits for those who have none yet."""
    known: dict[int, tuple[float, float, float, bool, float, float]] = {
        r.player_id: (r.peak_age, r.decline_age, float(r.ceiling_bonus), bool(r.ageless),
                      r.progress, r.trend)
        for r in conn.execute(select(player_development))}
    missing = [k for k, pid in enumerate(ids) if pid not in known]
    if missing:
        drawn = draw_traits(world.defs.development, potential[missing],
                            derive_rng(meta.seed, "development-traits", day.isoformat()))
        rows = []
        for n, k in enumerate(missing):
            entry = (float(drawn.peak_age[n]), float(drawn.decline_age[n]),
                     float(drawn.ceiling_bonus[n]), bool(drawn.ageless[n]), 0.0, 0.0)
            known[ids[k]] = entry
            rows.append({"player_id": ids[k], "peak_age": entry[0], "decline_age": entry[1],
                         "ceiling_bonus": int(entry[2]), "ageless": int(entry[3]),
                         "progress": 0.0, "trend": 0.0})
        conn.execute(player_development.insert(), rows)
    state = np.array([known[pid] for pid in ids], dtype=float)
    traits = Traits(peak_age=state[:, 0], decline_age=state[:, 1], ceiling_bonus=state[:, 2],
                    ageless=state[:, 3] > 0.5)
    return traits, state[:, 4].copy(), state[:, 5].copy()


def _development_news(conn: Connection, world: World, meta: CareerMeta, rows: Sequence[Row[Any]],
                      groups: list[Any], before: np.ndarray, after: np.ndarray,
                      moves: np.ndarray) -> list[str]:
    if meta.user_club_id is None:
        return []
    ours = {r.person_id for r in conn.execute(select(contract.c.person_id).where(
        contract.c.club_id == meta.user_club_id, contract.c.is_active == 1))}
    index = [k for k, r in enumerate(rows) if r.id in ours]
    if not index:
        return []
    old = world.model.group_overalls(before[index])
    new = world.model.group_overalls(after[index])
    changes = []
    least = world.defs.development.news_min_change
    for n, k in enumerate(index):
        before_k, after_k = float(old[groups[k]][n]), float(new[groups[k]][n])
        was, now = round(before_k), round(after_k)
        if now != was and abs(after_k - before_k) >= least:
            r = rows[k]
            name = display_name(r.first_name, r.last_name, r.known_as)
            whole = " (every attribute up)" if moves[k] > 0 else (
                " (every attribute down)" if moves[k] < 0 else "")
            changes.append((now - was, f"{name} {was}→{now}{whole}"))
    if not changes:
        return []
    up = [text_ for change, text_ in sorted(changes, key=lambda m: -m[0]) if change > 0]
    down = [text_ for change, text_ in sorted(changes, key=lambda m: m[0]) if change < 0]
    parts = []
    if up:
        parts.append(f"Improved: {', '.join(up)}.")
    if down:
        parts.append(f"Declined: {', '.join(down)}.")
    return ["Player development. " + " ".join(parts)]


def _renew_contracts(conn: Connection, meta: CareerMeta, season_start: date,
                     season_end: date) -> None:
    """Until the transfer market exists, expiring contracts are simply extended."""
    expiring = conn.execute(select(contract.c.id, contract.c.person_id).where(
        contract.c.is_active == 1, contract.c.end_date < season_end.isoformat())).all()
    for row in expiring:
        years = 1 + int(derive_rng(meta.seed, "renewal", row.id, season_start).integers(0, 3))
        end = date(season_end.year + years - 1, 6, 30)
        conn.execute(update(contract).where(contract.c.id == row.id).values(
            end_date=end.isoformat()))


def refresh_ai_tactics(conn: Connection, world: World, meta: CareerMeta, day: date) -> None:
    """AI clubs in active leagues pick the formation that suits their squad best."""
    clubs = {cid for a in active_leagues(conn, world)
             for cid in members(conn, meta.season_id, a.competition_id)}
    existing = {r.club_id: r for r in conn.execute(select(tactic))}
    for club_id in sorted(clubs):
        if club_id == meta.user_club_id and club_id in existing:
            continue
        squad = load_squad(conn, club_id, day)
        if not squad:
            continue
        formation = world.picker.best_formation(club_id, "", squad, AI_FORMATIONS)
        values = {"formation": formation, "roles": json.dumps({}), "lineup": None,
                  "instructions": json.dumps(default_instructions(world.defs))}
        if club_id in existing:
            conn.execute(update(tactic).where(tactic.c.club_id == club_id).values(**values))
        else:
            conn.execute(tactic.insert().values(club_id=club_id, **values))


def next_day(day: date) -> date:
    return day + timedelta(days=1)
