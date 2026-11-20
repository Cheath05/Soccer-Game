"""Season lifecycle: fixtures, final tables, play-offs, promotion/relegation, rollover."""

import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
from sqlalchemy import Connection, Row, bindparam, func, select, text, update

from footsim.competitions.calendars import shifted_calendar
from footsim.competitions.fixtures import Round, grouped_rounds, round_robin, split_phases
from footsim.competitions.playoffs import Entrant, Seeds, legs_for, round_ties, series_winner
from footsim.competitions.scheduling import PLAYOFF_GAP, league_round_dates, playoff_dates
from footsim.competitions.standings import Result, TableRow, league_table
from footsim.core.rng import derive_rng, derive_seed
from footsim.defs.calendar import SeasonCalendarDef
from footsim.defs.competitions import (
    GroupsFormat,
    LeagueDef,
    MovementKind,
    PhaseDef,
    PlayoffDef,
    PlayoffRoundDef,
    SimLevel,
)
from footsim.domain.attributes import ATTRIBUTES
from footsim.match.report import Decider
from footsim.people.development import (
    DevelopmentInput,
    Traits,
    academy_boost,
    apply_month,
    draw_traits,
)
from footsim.persistence.schema import (
    club,
    club_league_membership,
    competition,
    contract,
    fixture,
    league_final,
    league_title,
    player_attr,
    player_development,
    playoff_tie,
    season,
    tactic,
)
from footsim.world.club_names import apply_club_names, apply_club_nations
from footsim.world.college.assistant import weekly as assistant_recruiting
from footsim.world.college.common import LOWER_REGULAR, is_college_stage, is_lower_stage
from footsim.world.college.draft import college_turnover
from footsim.world.college.lower import progress_lower
from footsim.world.college.program import growth_factors, progress_program
from footsim.world.college.recruiting import progress_recruiting
from footsim.world.college.season import (
    college_decider,
    create_college_fixtures,
    progress_college,
)
from footsim.world.college.visits import settle as settle_visits
from footsim.world.context import AI_FORMATIONS, World, default_instructions
from footsim.world.cups import blocked_dates, cup_decider, progress_cups, start_cups
from footsim.world.draft import draft_day
from footsim.world.europe.stages import europe_decider, progress_europe, start_europe
from footsim.world.finance import pay_merit, settle_month, start_season_finances
from footsim.world.international import ensure_international
from footsim.world.international.club_world_cup import club_world_cup_day, is_cwc
from footsim.world.international.club_world_cup import decider as cwc_decider
from footsim.world.international.common import SUMMER_TYPES
from footsim.world.international.common import TYPE as INTERNATIONAL_TYPE
from footsim.world.international.finals import decider as finals_decider
from footsim.world.international.finals import is_finals
from footsim.world.international.qualifiers import decider as qualifier_decider
from footsim.world.international.qualifiers import is_qualifier
from footsim.world.international.windows import FRIENDLY, international_day
from footsim.world.lifecycle import season_turnover
from footsim.world.loans import end_loans
from footsim.world.market import run_market
from footsim.world.meta import CareerMeta, bump_players_epoch
from footsim.world.mls import mls_month, new_mls_season
from footsim.world.news_scope import news_scope
from footsim.world.overall_history import record_season_start
from footsim.world.renewals import contract_reminders, settle_expiring
from footsim.world.reputation import drift_reputations
from footsim.world.squads import club_name, display_name, load_squad
from footsim.world.training import train_positions

DEVELOPMENT_SHARE = 1 / 12  # of a year's development, applied on the first of each month


@dataclass(frozen=True)
class ActiveLeague:
    competition_id: int
    league: LeagueDef


def season_calendar(world: World, meta: CareerMeta, season_id: int) -> SeasonCalendarDef:
    return shifted_calendar(world.defs.calendars[meta.base_calendar], season_id - 1)


def league_groups(conn: Connection, league: LeagueDef, clubs: Sequence[int]
                  ) -> dict[str, set[int]]:
    """Each conference's or zone's clubs among ``clubs`` (this season's members), found by name.
    Empty for a league without groups."""
    if not league.groups:
        return {}
    names = {r.id: r.name for r in conn.execute(select(club.c.id, club.c.name).where(
        club.c.id.in_(list(clubs))))}
    by_name = {name: cid for cid, name in names.items()}
    missing = [n for g in league.groups for n in g.clubs if n not in by_name]
    if missing:
        raise RuntimeError(f"{league.key}: clubs of its groups not in the league: {missing}")
    return {g.key: {by_name[n] for n in g.clubs} for g in league.groups}


def _club_ids(conn: Connection, names: Sequence[str]) -> dict[str, int]:
    return {r.name: r.id for r in conn.execute(select(club.c.id, club.c.name).where(
        club.c.name.in_(list(names))))}


def season_rounds(conn: Connection, league: LeagueDef, clubs: list[int],
                  rng: np.random.Generator) -> list[list[Round]]:
    """The season's league rounds, by phase (one run for a league without phases)."""
    phases = max(1, len(league.phases))
    fmt = league.format
    if isinstance(fmt, GroupsFormat):
        groups = league_groups(conn, league, clubs)
        ids = _club_ids(conn, [c for pair in fmt.rivals for c in pair])
        rivals = [(ids[a], ids[b]) for a, b in fmt.rivals]
        return grouped_rounds([sorted(groups[g.key]) for g in league.groups], fmt.legs,
                              fmt.cross_rounds, rivals, phases, rng)
    return split_phases(round_robin(clubs, fmt.legs * phases, rng), phases)


def league_calendar(world: World, league: LeagueDef, season_id: int) -> SeasonCalendarDef:
    """A league's own calendar for a season: its country's dates. Every calendar shares the
    career's season boundaries (1 July to 30 June), so every league turns over together."""
    return shifted_calendar(world.defs.calendars[league.calendar], season_id - 1)


def ensure_leagues(conn: Connection, world: World, season_id: int) -> list[str]:
    """Leagues the definitions have and the save doesn't (a world built before them, or a
    career from before them): their competitions, and their clubs for the season, found by the
    ratings source's names for the league. A league whose clubs don't add up is left out, so a
    rollover can't end up with leagues of the wrong size. Returns news.

    First, clubs a save has under the source's names or nation get their real ones
    (world/club_names.yaml, club_nations.yaml: Liga MX's accents, MLS's Canadian clubs), so a
    career from before them has them as their league begins. Both are idempotent."""
    apply_club_names(conn)
    apply_club_nations(conn)
    existing = {r.key for r in conn.execute(select(competition.c.key))}
    nation_ids = {r.code: r.id for r in conn.execute(text("SELECT id, code FROM nation"))}
    taken = {r.club_id for r in conn.execute(select(club_league_membership.c.club_id).where(
        club_league_membership.c.season_id == season_id))}
    added = []
    for key, league in sorted(world.defs.leagues.items(),
                              key=lambda kv: (kv[1].nation, kv[1].tier)):
        if key in existing or league.sim_level is SimLevel.DORMANT or not league.source_leagues:
            continue
        clubs = [r.id for r in conn.execute(
            text("SELECT id FROM club WHERE source_league IN :names ORDER BY id")
            .bindparams(bindparam("names", expanding=True)), {"names": league.source_leagues})
            if r.id not in taken]
        if len(clubs) != league.clubs:
            continue
        inserted = conn.execute(competition.insert().values(
            key=key, name=league.name, short_name=league.short_name,
            nation_id=nation_ids.get(league.nation), type="league", tier=league.tier,
            sim_level=league.sim_level.value))
        competition_id = inserted.inserted_primary_key[0] if inserted.inserted_primary_key else None
        conn.execute(club_league_membership.insert(), [
            {"club_id": c, "season_id": season_id, "competition_id": competition_id}
            for c in clubs])
        taken.update(clubs)
        added.append(league.name)
    if not added:
        return []
    return [f"New leagues: {', '.join(added)} are played from this season. Their tables are "
            "on the League page."]


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
    first-round draws of every country's cups. Returns news of the draws."""
    news = ensure_leagues(conn, world, season_id)
    for active in active_leagues(conn, world):
        league = active.league
        clubs = members(conn, season_id, active.competition_id)
        rng = derive_rng(meta.seed, "fixtures", season_id, league.key)
        own = league_calendar(world, league, season_id)
        first = 1
        phases: list[PhaseDef | None] = list(league.phases) or [None]
        for phase, rounds in zip(phases, season_rounds(conn, league, clubs, rng), strict=True):
            dated = own.competitions[league.calendar_key(phase.key if phase else None)]
            dates = league_round_dates(dated, own, len(rounds),
                                       blocked_dates(world, own, league.key))
            conn.execute(fixture.insert(), [
                {"season_id": season_id, "competition_id": active.competition_id,
                 "stage": "league", "round": number, "date": day.isoformat(),
                 "home_club_id": home, "away_club_id": away, "neutral": 0,
                 "status": "scheduled"}
                for number, (games, day) in enumerate(zip(rounds, dates, strict=True),
                                                      start=first)
                for home, away in games
            ])
            first += len(rounds)
    news += create_college_fixtures(conn, world, meta, season_id,
                                    season_calendar(world, meta, season_id).season_start)
    news += start_cups(conn, world, meta, meta.current_date)
    return news + start_europe(conn, world, meta, season_id, meta.current_date)


def league_results(conn: Connection, competition_id: int, season_id: int,
                   rounds: tuple[int, int] | None = None) -> list[Result]:
    """The season's played league results; ``rounds``: only those of these rounds (a phase)."""
    query = select(fixture).where(
        fixture.c.competition_id == competition_id, fixture.c.season_id == season_id,
        fixture.c.stage == "league", fixture.c.status == "played",
    )
    if rounds is not None:
        query = query.where(fixture.c.round.between(*rounds))
    return [Result(r.home_club_id, r.away_club_id, r.home_goals, r.away_goals)
            for r in conn.execute(query)]


def phase_rounds(conn: Connection, league: LeagueDef, competition_id: int, season_id: int,
                 phase: str) -> tuple[int, int]:
    """The first and last league round of a phase: the season's rounds split evenly."""
    total = int(conn.execute(select(func.max(fixture.c.round)).where(
        fixture.c.competition_id == competition_id, fixture.c.season_id == season_id,
        fixture.c.stage == "league")).scalar() or 0)
    size = total // len(league.phases)
    k = [p.key for p in league.phases].index(phase)
    return k * size + 1, (k + 1) * size


def standings(conn: Connection, world: World, meta: CareerMeta, competition_id: int,
              season_id: int, phase: str | None = None) -> list[TableRow]:
    """The season's table (every league match), or a phase's (its rounds only)."""
    key: str = conn.execute(select(competition.c.key).where(competition.c.id == competition_id)
                            ).scalar_one()
    league = world.defs.leagues[key]
    rounds = (phase_rounds(conn, league, competition_id, season_id, phase)
              if phase is not None else None)
    lots = (derive_seed(meta.seed, "lots", season_id, key) if phase is None
            else derive_seed(meta.seed, "lots", season_id, key, phase))
    return league_table(members(conn, season_id, competition_id),
                        league_results(conn, competition_id, season_id, rounds), league.points,
                        league.tiebreakers, lots)


def group_table(rows: Sequence[TableRow], clubs: set[int]) -> list[TableRow]:
    """A conference's or zone's table: the league table's rows of its clubs, in the league's
    order (every match counts, the other group's too), renumbered."""
    return [TableRow(**{**vars(r), "position": k})
            for k, r in enumerate((r for r in rows if r.club_id in clubs), start=1)]


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
    """Close finished leagues and phases, start and advance play-offs, and on the first of each
    month let players develop and settle every club's month of money; in a transfer window the
    AI clubs trade (world/market.py). Returns news messages."""
    messages: list[str] = []
    if day.day == 1:
        messages += ensure_international(conn, world, meta, day)  # a save from before W8
        messages += develop_players(conn, world, meta, day, DEVELOPMENT_SHARE)
        settle_month(conn, world, meta, day, _league_positions(conn, world, meta))
        messages += train_positions(conn, world, meta, day)
        messages += contract_reminders(conn, world, meta, day,
                                       season_calendar(world, meta, meta.season_id).season_end)
        messages += mls_month(conn, world, meta, day)
    scope = news_scope(conn, world, meta)  # the news of leagues the user doesn't follow is left out
    messages += progress_cups(conn, world, meta, day, scope)
    europe = progress_europe(conn, world, meta, day)
    messages += [] if scope.quiet_world else europe
    for active in active_leagues(conn, world):
        cid, league = active.competition_id, active.league
        news: list[str] = []
        for phase in league.phases:
            news += _progress_phase(conn, world, meta, cid, league, phase, day)
        if not _finalized(conn, cid, meta.season_id):
            if _scheduled(conn, cid, meta.season_id, "league") == 0:
                news += _finalize_league(conn, world, meta, cid, league, day)
        else:
            for playoff in league.playoffs:
                if playoff.phase is None:
                    news += _progress_playoff(conn, world, meta, cid, league, playoff, day)
        if scope.follows_league(league.key):
            messages += news
    messages += progress_college(conn, world, meta, day)
    messages += progress_lower(conn, world, meta, day)
    messages += progress_recruiting(conn, world, meta, day)
    messages += settle_visits(conn, world, meta, day)
    messages += assistant_recruiting(conn, world, meta, day)
    messages += progress_program(conn, world, meta, day)
    messages += international_day(conn, world, meta, day)
    club_world_cup = club_world_cup_day(conn, world, meta, day)
    messages += [] if scope.quiet_world else club_world_cup
    messages += draft_day(conn, world, meta, day)
    messages += end_loans(conn, meta, day)
    messages += run_market(conn, world, meta, day,
                           season_calendar(world, meta, meta.season_id).season_end)
    return messages


def _league_positions(conn: Connection, world: World,
                      meta: CareerMeta) -> dict[int, tuple[int, int]]:
    """Every league club's place this season, and its league matches played."""
    result: dict[int, tuple[int, int]] = {}
    for active in active_leagues(conn, world):
        for row in standings(conn, world, meta, active.competition_id, meta.season_id):
            result[row.club_id] = (row.position, row.played)
    return result


def _seeds(conn: Connection, world: World, meta: CareerMeta, competition_id: int,
           league: LeagueDef, phase: str | None) -> Seeds:
    """The table a play-off seeds from (the season's, or a phase's), by league rank and by rank
    within each group."""
    rows = standings(conn, world, meta, competition_id, meta.season_id, phase)
    groups = league_groups(conn, league, [r.club_id for r in rows])
    return Seeds.of([r.club_id for r in rows], groups)


def _entrants(seeds: Seeds, playoff: PlayoffDef) -> set[int]:
    """The clubs a play-off's ranks name."""
    return ({seeds.ranks[r] for r in playoff.entrant_ranks()}
            | {seeds.groups[g][r] for g, r in playoff.group_ranks()})


def _record_title(conn: Connection, meta: CareerMeta, competition_id: int, title: str,
                  club_id: int, kind: str, day: date, phase: str | None = None) -> bool:
    """A title won; False if it was recorded already."""
    exists = conn.execute(select(league_title.c.club_id).where(
        league_title.c.season_id == meta.season_id,
        league_title.c.competition_id == competition_id, league_title.c.title == title)).first()
    if exists is not None:
        return False
    conn.execute(league_title.insert().values(
        season_id=meta.season_id, competition_id=competition_id, title=title, club_id=club_id,
        kind=kind, phase=phase, won_on=day.isoformat()))
    return True


def phase_title(league: LeagueDef, phase: PhaseDef) -> str:
    return f"{league.short_name} {phase.name}"


def _progress_phase(conn: Connection, world: World, meta: CareerMeta, competition_id: int,
                    league: LeagueDef, phase: PhaseDef, day: date) -> list[str]:
    """A phase whose rounds are all played: its play-offs begin (or, with none, its table's top
    club is its champion), and they advance."""
    first, last = phase_rounds(conn, league, competition_id, meta.season_id, phase.key)
    if last < first:
        return []
    left = conn.execute(select(func.count()).select_from(fixture).where(
        fixture.c.competition_id == competition_id, fixture.c.season_id == meta.season_id,
        fixture.c.stage == "league", fixture.c.status == "scheduled",
        fixture.c.round.between(first, last))).scalar_one()
    if left:
        return []
    playoffs = [p for p in league.playoffs if p.phase == phase.key]
    messages: list[str] = []
    for playoff in playoffs:
        started = conn.execute(select(playoff_tie.c.id).where(
            playoff_tie.c.season_id == meta.season_id,
            playoff_tie.c.playoff_key == playoff.key)).first()
        if started is None:
            seeds = _seeds(conn, world, meta, competition_id, league, phase.key)
            _create_playoff_round(conn, world, meta, competition_id, league, playoff, 0,
                                  seeds, {})
            leader = club_name(conn, seeds.ranks[1])
            messages.append(f"{leader} top the {phase_title(league, phase)} table; the "
                            f"{playoff.name} begins.")
        else:
            messages += _progress_playoff(conn, world, meta, competition_id, league, playoff,
                                          day)
    if not any(p.title for p in playoffs):
        top = standings(conn, world, meta, competition_id, meta.season_id, phase.key)[0].club_id
        title = phase_title(league, phase)
        if _record_title(conn, meta, competition_id, title, top, "champion", day, phase.key):
            messages.append(f"{club_name(conn, top)} are {title} champions.")
    return messages


def _finalize_league(conn: Connection, world: World, meta: CareerMeta, competition_id: int,
                     league: LeagueDef, day: date) -> list[str]:
    table = standings(conn, world, meta, competition_id, meta.season_id)
    seeds = Seeds.of([r.club_id for r in table],
                     league_groups(conn, league, [r.club_id for r in table]))
    outcome: dict[int, str] = {}  # by club
    for mv in league.movements:
        label = "promoted" if mv.kind is MovementKind.PROMOTION else "relegated"
        for pos in range(mv.ranks[0], mv.ranks[1] + 1):
            outcome[seeds.ranks[pos]] = label
    for playoff in league.playoffs:
        if playoff.phase is None:
            for club_id in _entrants(seeds, playoff):
                outcome[club_id] = "playoffs"
    leader = table[0].club_id
    champion = club_name(conn, leader)
    if league.table_title is not None:
        outcome[leader] = "table_title"
        _record_title(conn, meta, competition_id, league.table_title, leader, "award", day)
        messages = [f"{champion} win the {league.table_title}."]
    elif league.title_playoff is None and not league.phases:
        outcome[leader] = "champion"
        _record_title(conn, meta, competition_id, league.name, leader, "champion", day)
        messages = [f"{champion} are {league.name} champions."]
    else:
        messages = [f"{champion} top the {league.name} table."] if league.phases else []
    conn.execute(league_final.insert(), [
        {"season_id": meta.season_id, "competition_id": competition_id, "club_id": row.club_id,
         "position": row.position, "played": row.played, "won": row.won, "drawn": row.drawn,
         "lost": row.lost, "goals_for": row.goals_for, "goals_against": row.goals_against,
         "points": row.points, "outcome": outcome.get(row.club_id)}
        for row in table
    ])
    pay_merit(conn, world, meta, league.key, competition_id,
              [(row.position, row.club_id) for row in table], day)
    for playoff in league.playoffs:
        if playoff.phase is None:
            _create_playoff_round(conn, world, meta, competition_id, league, playoff, 0,
                                  seeds, {})
    return messages


def _create_playoff_round(conn: Connection, world: World, meta: CareerMeta, competition_id: int,
                          league: LeagueDef, playoff: PlayoffDef, round_index: int,
                          seeds: Seeds, winners: dict[str, Entrant]) -> None:
    calendar = league_calendar(world, league, meta.season_id)
    dates_cfg = calendar.competitions[league.calendar_key(playoff.phase)]
    leg_dates = playoff_dates(dates_cfg.end, dates_cfg.playoffs_end, playoff.rounds)[round_index]
    rnd = playoff.rounds[round_index]
    for tie in round_ties(playoff, round_index, seeds, winners):
        conn.execute(playoff_tie.insert().values(
            season_id=meta.season_id, competition_id=competition_id, playoff_key=playoff.key,
            tie=tie.tie_id, round=round_index, club_a_id=tie.a.club_id, club_b_id=tie.b.club_id,
            rank_a=tie.a.rank, rank_b=tie.b.rank,
        ))
        legs = legs_for(tie, rnd)
        if rnd.games > 1:  # a series: the games one club needs to win it, the rest if needed
            legs = legs[:rnd.games // 2 + 1]
        for leg, day in zip(legs, leg_dates, strict=False):
            _insert_tie_match(conn, meta, competition_id, playoff, round_index, tie.tie_id, rnd,
                              leg.home, leg.away, leg.leg, leg.neutral, day)


def _insert_tie_match(conn: Connection, meta: CareerMeta, competition_id: int,
                      playoff: PlayoffDef, round_index: int, tie_id: str, rnd: PlayoffRoundDef,
                      home: int, away: int, leg: int | None, neutral: bool, day: date) -> None:
    """One match of a play-off tie. A series' games are ties of their own (``E1:2``), so no
    game is read as the second leg of another."""
    conn.execute(fixture.insert().values(
        season_id=meta.season_id, competition_id=competition_id, stage=playoff.key,
        round=round_index, tie=f"{tie_id}:{leg}" if rnd.games > 1 else tie_id,
        leg=leg, date=day.isoformat(), home_club_id=home, away_club_id=away,
        neutral=int(neutral), status="scheduled",
    ))


def _tie_games(conn: Connection, season_id: int, playoff: PlayoffDef, rnd: PlayoffRoundDef,
               tie_id: str) -> list[Row[Any]]:
    ties = ([f"{tie_id}:{g}" for g in range(1, rnd.games + 1)] if rnd.games > 1 else [tie_id])
    return list(conn.execute(select(fixture).where(
        fixture.c.season_id == season_id, fixture.c.stage == playoff.key,
        fixture.c.tie.in_(ties)).order_by(fixture.c.leg)).all())


def _tie_winner(conn: Connection, meta: CareerMeta, competition_id: int, playoff: PlayoffDef,
                tie: Row[Any]) -> int | None:
    """A tie's winner once it's decided; a series still level after its games so far gets its
    next game."""
    rnd = playoff.rounds[tie.round]
    games = _tie_games(conn, meta.season_id, playoff, rnd, tie.tie)
    if not games or any(g.status != "played" for g in games):
        return None
    if rnd.games > 1:
        winner = series_winner(tie.club_a_id, tie.club_b_id, rnd.games, [
            (g.home_club_id, g.away_club_id, g.home_goals, g.away_goals, g.home_pens,
             g.away_pens) for g in games])
        if winner is None and len(games) < rnd.games:
            last = games[-1]
            day = date.fromisoformat(last.date) + timedelta(days=PLAYOFF_GAP)
            better = tie.club_a_id if rnd.host == "higher_ranked" else tie.club_b_id
            other = tie.club_b_id if better == tie.club_a_id else tie.club_a_id
            game = len(games) + 1
            home, away = (better, other) if game % 2 else (other, better)
            _insert_tie_match(conn, meta, competition_id, playoff, tie.round, tie.tie, rnd,
                              home, away, game, False, day)
        return winner
    goals = {tie.club_a_id: 0, tie.club_b_id: 0}
    for g in games:
        goals[g.home_club_id] += g.home_goals
        goals[g.away_club_id] += g.away_goals
    a, b = int(tie.club_a_id), int(tie.club_b_id)
    if goals[a] != goals[b]:
        return a if goals[a] > goals[b] else b
    if rnd.higher_seed_on_level:
        return a if tie.rank_a <= tie.rank_b else b
    last = games[-1]
    if last.home_pens is None:
        return None
    winner_: int = last.home_club_id if last.home_pens > last.away_pens else last.away_club_id
    return winner_


def _progress_playoff(conn: Connection, world: World, meta: CareerMeta, competition_id: int,
                      league: LeagueDef, playoff: PlayoffDef, day: date) -> list[str]:
    ties = conn.execute(select(playoff_tie).where(
        playoff_tie.c.season_id == meta.season_id, playoff_tie.c.playoff_key == playoff.key,
    )).all()
    if not ties:
        return []
    for t in ties:
        if t.winner_club_id is None:
            winner = _tie_winner(conn, meta, competition_id, playoff, t)
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
        seeds = _seeds(conn, world, meta, competition_id, league, playoff.phase)
        rank_of = seeds.rank_of
        winners = {t.tie: Entrant(t.winner_club_id, rank_of[t.winner_club_id]) for t in ties
                   if t.winner_club_id is not None}
        _create_playoff_round(conn, world, meta, competition_id, league, playoff, current + 1,
                              seeds, winners)
        return []
    champion = in_round[0].winner_club_id
    if playoff.title:
        phase = next((p for p in league.phases if p.key == playoff.phase), None)
        title = phase_title(league, phase) if phase is not None else playoff.name
        if not _record_title(conn, meta, competition_id, title, champion, "champion", day,
                             playoff.phase):
            return []
        if phase is None:
            conn.execute(update(league_final).where(
                league_final.c.season_id == meta.season_id, league_final.c.club_id == champion,
                league_final.c.competition_id == competition_id,
            ).values(outcome="champion"))
            return [f"{club_name(conn, champion)} win {playoff.name}: they are the "
                    f"{league.name} champions."]
        return [f"{club_name(conn, champion)} win the {playoff.name}: they are {title} "
                "champions."]
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
    if fx.stage in ("league", FRIENDLY):
        return None
    if is_qualifier(fx.stage):
        return qualifier_decider(conn, world, fx)
    if is_cwc(fx.stage):
        return cwc_decider(fx)
    if is_finals(fx.stage):
        return finals_decider(fx)
    if fx.stage == LOWER_REGULAR:  # D-II/D-III regular season (W9e): draws stand
        return None
    if is_lower_stage(fx.stage):  # D-II/D-III national tournaments
        return Decider(extra_time=True, penalties=True)
    if is_college_stage(fx.stage):
        return college_decider(world, fx.stage)
    if fx.stage in world.defs.cups:
        return cup_decider(conn, world, fx)
    if fx.stage in world.defs.continental:
        return europe_decider(conn, world, fx)
    comp_key: str = conn.execute(select(competition.c.key).where(
        competition.c.id == fx.competition_id)).scalar_one()
    playoff = next(p for p in world.defs.leagues[comp_key].playoffs if p.key == fx.stage)
    rnd = playoff.rounds[fx.round]
    if rnd.legs == 1:  # a single match, or a series' game: decided on the day
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
    """Whether every fixture of the season is played. International football (and the Club
    World Cup) runs into July, so it doesn't hold the rollover up (world/international)."""
    summer = select(competition.c.id).where(competition.c.type.in_(SUMMER_TYPES))
    return conn.execute(select(func.count()).select_from(fixture).where(
        fixture.c.season_id == season_id, fixture.c.status == "scheduled",
        fixture.c.competition_id.not_in(summer),
    )).scalar_one() == 0


def rollover(conn: Connection, world: World, meta: CareerMeta) -> list[str]:
    """Start the next season: promotion/relegation, development, contracts, fixtures."""
    old, new = meta.season_id, meta.season_id + 1
    calendar = season_calendar(world, meta, new)
    conn.execute(season.insert().values(id=new, label=calendar.season,
                                        start_date=calendar.season_start.isoformat(),
                                        end_date=calendar.season_end.isoformat()))
    # International fixtures drawn ahead (qualifiers run over seasons) belong to the season
    # they're played in.
    conn.execute(text(
        "UPDATE fixture SET season_id = :new WHERE season_id = :old AND status = 'scheduled' "
        "AND date >= :start AND competition_id IN (SELECT id FROM competition WHERE type = :t)"),
        {"new": new, "old": old, "start": calendar.season_start.isoformat(),
         "t": INTERNATIONAL_TYPE})
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
    scope = news_scope(conn, world, meta)
    for club_id, target in sorted(moves.items()):
        new_league = world.defs.leagues[key_of[target]]
        old_league = world.defs.leagues[key_of[previous[club_id]]]
        if not (scope.follows_league(new_league.key) or scope.follows_league(old_league.key)):
            continue
        verb = "promoted to" if new_league.tier < old_league.tier else "relegated to"
        messages.append(f"{club_name(conn, club_id)} {verb} the {new_league.name}.")

    messages += season_turnover(conn, world, meta, calendar.season_start)
    messages += college_turnover(conn, world, meta, new, calendar.season_start)
    record_season_start(conn, world, new, calendar.season_start)
    messages += settle_expiring(conn, world, meta, calendar.season_start - timedelta(days=1),
                                calendar.season_end)
    conn.execute(text("UPDATE player_state SET season_yellows = 0"))
    meta.season_id = new
    refresh_ai_tactics(conn, world, meta, calendar.season_start)
    messages += create_season_fixtures(conn, world, meta, new)
    messages += drift_reputations(conn, world, meta, old, new)
    # MLS's allocations and roster rules for the new season, before the budgets are set (the
    # first season the save has MLS sets its squads' wages: world/mls.py).
    messages += new_mls_season(conn, world, meta, old, calendar.season_start)
    start_season_finances(conn, world, meta, old, calendar.season_start)
    messages.insert(0, f"The {calendar.season} season begins.")
    return messages


def develop_players(conn: Connection, world: World, meta: CareerMeta, day: date,
                    share: float) -> list[str]:
    """A month of development for every player (people/development.py): the young grow
    towards their ceilings, faster with minutes played in the past twelve months (and a little
    for being named a substitute without coming on: the bench credit, which then fades), and
    the old decline. Academy products who play regularly have their potential raised a little.
    Traits are drawn the first time a player needs them. Returns news of the user's players
    whose overall moved. ``share`` is kept for callers; a step is always a month."""
    rows = conn.execute(text("""
        SELECT p.id, p.first_name, p.last_name, p.known_as, p.birth_date, pl.pa_hidden,
               (SELECT position FROM player_position pp WHERE pp.player_id = p.id
                ORDER BY familiarity DESC LIMIT 1) AS position,
               COALESCE((SELECT SUM(minutes) FROM player_match pm JOIN fixture f
                         ON f.id = pm.fixture_id WHERE pm.player_id = p.id
                         AND f.date > :since AND f.date <= :day), 0) AS minutes,
               COALESCE(s.bench_minutes, 0) AS bench_minutes
        FROM person p JOIN player pl ON pl.person_id = p.id
        LEFT JOIN player_state s ON s.player_id = p.id
        WHERE pl.retired_on IS NULL
        ORDER BY p.id
    """), {"since": (day - timedelta(days=365)).isoformat(), "day": day.isoformat()}).all()
    attrs_rows = {r.player_id: r for r in conn.execute(select(player_attr))}
    ids = [r.id for r in rows]
    matrix = np.array([[getattr(attrs_rows[i], a) for a in ATTRIBUTES] for i in ids], dtype=float)
    groups = [world.defs.positions[r.position or "CM"].group for r in rows]
    potential = np.array([r.pa_hidden for r in rows], dtype=float)
    traits, progress, trend, boost = _development_state(conn, world, meta, day, ids, potential)
    rules = world.defs.development
    ages = np.array([(day - date.fromisoformat(r.birth_date)).days / 365.25 for r in rows])
    minutes = np.array([r.minutes for r in rows], dtype=float)
    boost, points = academy_boost(rules, ages, minutes, _academy_products(conn, ids), potential,
                                  boost)
    # The program builder's training facilities speed their college players' growth (W9d).
    factors = growth_factors(conn, world)
    inp = DevelopmentInput(
        attrs=matrix,
        ages=ages,
        potential=potential + points,  # this month's growth already aims at the raised ceiling
        groups=groups,
        minutes=minutes,
        bench_minutes=np.array([r.bench_minutes for r in rows], dtype=float),
        growth_factor=(np.array([factors.get(i, 1.0) for i in ids], dtype=float)
                       if factors else None),
    )
    new, progress, moves = apply_month(rules, world.model, inp, traits, progress,
                                       derive_rng(meta.seed, "development", day.isoformat()))
    moved = _own_overalls(world, new, groups) - _own_overalls(world, matrix, groups)
    trend = rules.trend_memory * trend + (1 - rules.trend_memory) * moved
    changed = np.any(new != matrix, axis=1)
    params = [{"pid": ids[i], **{a: int(new[i, j]) for j, a in enumerate(ATTRIBUTES)}}
              for i in np.flatnonzero(changed)]
    if params:
        assignments = ", ".join(f"{a} = :{a}" for a in ATTRIBUTES)
        conn.execute(text(f"UPDATE player_attr SET {assignments} WHERE player_id = :pid"), params)
        bump_players_epoch(conn)
    conn.execute(text("UPDATE player_development SET progress = :progress, trend = :trend, "
                      "potential_boost = :boost WHERE player_id = :pid"),
                 [{"pid": pid, "progress": float(p), "trend": float(t), "boost": float(b)}
                  for pid, p, t, b in zip(ids, progress, trend, boost, strict=True)])
    raised = [{"pid": ids[i], "points": int(points[i])} for i in np.flatnonzero(points)]
    if raised:  # the academy boost's whole points reach his potential
        conn.execute(text("UPDATE player SET pa_hidden = pa_hidden + :points "
                          "WHERE person_id = :pid"), raised)
    # This month's growth has counted the bench credit; now it fades, so it can't pile up.
    conn.execute(text("UPDATE player_state SET bench_minutes = bench_minutes * :decay "
                      "WHERE bench_minutes > 0"), {"decay": rules.bench_decay})
    return _development_news(conn, world, meta, rows, groups, matrix, new, moves)


def _own_overalls(world: World, attrs: np.ndarray, groups: list[Any]) -> np.ndarray:
    """Each player's overall in his own position group."""
    overalls = world.model.group_overalls(attrs)
    return np.array([overalls[g][i] for i, g in enumerate(groups)])


def _academy_products(conn: Connection, ids: list[int]) -> np.ndarray:
    """Which of ``ids`` came up through the academy of the club they play for now: they have, or
    had, a youth contract with it. A player plays for the club holding his current contract; on
    loan, that is the borrower (a loaned-out player's own contract doesn't count while the loan
    runs), so he isn't an academy product there. Players sold on, or who never had a youth
    contract, aren't."""
    products = {r.person_id for r in conn.execute(text("""
        SELECT DISTINCT y.person_id FROM contract y
        JOIN contract k ON k.person_id = y.person_id AND k.club_id = y.club_id AND k.is_active = 1
        WHERE y.kind = 'youth' AND (k.kind = 'loan' OR NOT EXISTS (
            SELECT 1 FROM contract l
            WHERE l.person_id = k.person_id AND l.kind = 'loan' AND l.is_active = 1))"""))}
    return np.array([pid in products for pid in ids], dtype=bool)


def _development_state(conn: Connection, world: World, meta: CareerMeta, day: date,
                       ids: list[int], potential: np.ndarray
                       ) -> tuple[Traits, np.ndarray, np.ndarray, np.ndarray]:
    """Every player's traits, progress, trend and academy boost so far, drawing traits for those
    who have none yet."""
    known: dict[int, tuple[float, float, float, bool, float, float, float]] = {
        r.player_id: (r.peak_age, r.decline_age, float(r.ceiling_bonus), bool(r.ageless),
                      r.progress, r.trend, r.potential_boost)
        for r in conn.execute(select(player_development))}
    missing = [k for k, pid in enumerate(ids) if pid not in known]
    if missing:
        drawn = draw_traits(world.defs.development, potential[missing],
                            derive_rng(meta.seed, "development-traits", day.isoformat()))
        rows = []
        for n, k in enumerate(missing):
            entry = (float(drawn.peak_age[n]), float(drawn.decline_age[n]),
                     float(drawn.ceiling_bonus[n]), bool(drawn.ageless[n]), 0.0, 0.0, 0.0)
            known[ids[k]] = entry
            rows.append({"player_id": ids[k], "peak_age": entry[0], "decline_age": entry[1],
                         "ceiling_bonus": int(entry[2]), "ageless": int(entry[3]),
                         "progress": 0.0, "trend": 0.0, "potential_boost": 0.0})
        conn.execute(player_development.insert(), rows)
    state = np.array([known[pid] for pid in ids], dtype=float)
    traits = Traits(peak_age=state[:, 0], decline_age=state[:, 1], ceiling_bonus=state[:, 2],
                    ageless=state[:, 3] > 0.5)
    return traits, state[:, 4].copy(), state[:, 5].copy(), state[:, 6].copy()


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
