"""Read models for the API: squad lists, tables, fixtures, match reports, tactics."""

import json
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import Connection, Row, bindparam, func, or_, select, text

from footsim.api.honours import european_runs, treble, trophy_cabinet
from footsim.api.schemas import (
    AttributeOut,
    CareerOut,
    ClubHistoryOut,
    ClubOption,
    ClubOverviewOut,
    ClubPlayerOut,
    ClubRef,
    ClubSearchOut,
    ClubSeasonOut,
    CollegeCareerOut,
    CollegePlayerOut,
    CollegeSeasonRecordOut,
    CompetitionOut,
    CupOut,
    CupRoundOut,
    CupRunOut,
    CupSummaryOut,
    CupTieOut,
    EuropePlaceOut,
    FixtureOut,
    FormationOut,
    GroupTableOut,
    InstructionOut,
    InternationalCareerOut,
    LeagueOption,
    LeaguePlayoffOut,
    MatchEventOut,
    MatchOut,
    NationalTeamOut,
    PlayerDetailOut,
    PlayerLineOut,
    PlayerSeasonLineOut,
    PlayerSeasonOut,
    PositionRatingOut,
    PotentialOut,
    RatingAdjustmentOut,
    RoleOut,
    RoleRatingOut,
    SeasonOut,
    SheetEntryOut,
    SlotOut,
    SquadPlayerOut,
    TableOut,
    TableRowOut,
    TableViewOut,
    TacticsOut,
    TitleOut,
)
from footsim.competitions.scheduling import playoff_dates
from footsim.competitions.standings import TableRow
from footsim.core.text import ordinal
from footsim.defs.college import CLASS_NAMES
from footsim.defs.competitions import LeagueDef, MovementKind
from footsim.domain.attributes import ATTRIBUTE_GROUP, ATTRIBUTES
from footsim.importers.generate import age_on
from footsim.match.engine.clock import event_label
from footsim.match.teams import (
    BENCH_SIZE,
    SheetPlayer,
    SquadPlayer,
    TeamSheet,
    condition_factor,
    sub_order,
)
from footsim.persistence.database import open_database
from footsim.persistence.schema import (
    club,
    club_finance,
    club_league_membership,
    college_player,
    college_team,
    competition,
    continental_entry,
    cup_tie,
    fixture,
    league_final,
    league_title,
    nation,
    person,
    player_attr,
    player_position,
    player_season_overall,
    player_trait,
    playoff_tie,
    season,
    tactic,
)
from footsim.ratings.face import face_stats
from footsim.ratings.overall import familiarity_factor
from footsim.scouting.estimates import (
    OTHER_CLUB_KNOWLEDGE,
    OWN_CLUB_KNOWLEDGE,
    potential_label,
    potential_range,
)
from footsim.transfers.valuation import value_eur, years_old
from footsim.world.club_names import load_club_names
from footsim.world.college.common import (
    CONFERENCE_PREFIX,
    LOWER_PREFIX,
    LOWER_REGULAR,
    LOWER_TYPE,
    in_college,
)
from footsim.world.college.common import REGULAR as REGULAR_SEASON
from footsim.world.college.draft import leave_program
from footsim.world.college.program import facilities_bonus
from footsim.world.college.season import conference_tables, rankings
from footsim.world.context import World, default_instructions, get_world
from footsim.world.cups import cups_in_play, season_cups
from footsim.world.europe.common import competitions_by_rank, stage_name
from footsim.world.europe.places import CountryPlace, country_places
from footsim.world.europe.qualifying import Node, node_of, round_name
from footsim.world.fast_sim import SIM as FAST_SIM
from footsim.world.international.common import TYPE as INTERNATIONAL
from footsim.world.international.common import is_national, nation_ids
from footsim.world.international.titles import world_titles
from footsim.world.meta import CareerMeta, read_meta
from footsim.world.money import money_text, quote
from footsim.world.season import (
    active_leagues,
    group_table,
    league_calendar,
    league_groups,
    phase_rounds,
    season_calendar,
    standings,
)
from footsim.world.squads import display_name, load_squad, short_name, team_sheet
from footsim.world.transfers import Move, MoveRefused, complete_move, owner_contract

# --- helpers --------------------------------------------------------------------------


def _club_names(conn: Connection) -> dict[int, str]:
    return {r.id: r.name for r in conn.execute(select(club.c.id, club.c.name))}


def _competitions(conn: Connection) -> dict[int, Row[Any]]:
    return {r.id: r for r in conn.execute(select(competition))}


# A two-legged tie's first legs, by (season, competition, round, tie).
FirstLegs = dict[tuple[int, int, int, str], Row[Any]]


def first_legs(conn: Connection, rows: Sequence[Row[Any]]) -> FirstLegs:
    """The played first legs of the ties the second-leg ``rows`` belong to. The rows' own first
    legs are used as they stand; at most one query fetches the rest."""
    found: FirstLegs = {}
    for r in rows:
        if r.leg == 1 and r.tie is not None and r.status == "played":
            found[(r.season_id, r.competition_id, r.round, r.tie)] = r
    missing = [r for r in rows if r.leg == 2 and r.tie is not None
               and (r.season_id, r.competition_id, r.round, r.tie) not in found]
    if missing:
        wanted = {(r.season_id, r.competition_id, r.round, r.tie) for r in missing}
        for first in conn.execute(select(fixture).where(
                fixture.c.leg == 1, fixture.c.status == "played",
                fixture.c.season_id.in_({k[0] for k in wanted}),
                fixture.c.competition_id.in_({k[1] for k in wanted}),
                fixture.c.round.in_({k[2] for k in wanted}),
                fixture.c.tie.in_({k[3] for k in wanted}))):
            found[(first.season_id, first.competition_id, first.round, first.tie)] = first
    return found


def _first_leg_goals(row: Row[Any], firsts: FirstLegs) -> tuple[int, int] | None:
    """A second leg's first-leg goals, for the second leg's home and away clubs (the first leg
    was played the other way round); None on anything else, or while the first leg is unplayed."""
    if row.leg != 2 or row.tie is None:
        return None
    first = firsts.get((row.season_id, row.competition_id, row.round, row.tie))
    if (first is None or first.home_goals is None or first.away_goals is None
            or first.home_club_id != row.away_club_id or first.away_club_id != row.home_club_id):
        return None
    return first.away_goals, first.home_goals


def _college_stage(stage: str, round_: int) -> str:
    """A college fixture's stage (W9a): the regular season, a conference's tournament, or the
    NCAA tournament's round (its bracket rounds count from 0)."""
    college = get_world().defs.college
    if stage == REGULAR_SEASON:
        return "Regular season"
    if stage.startswith(CONFERENCE_PREFIX):
        conference = college.conferences.get(stage[len(CONFERENCE_PREFIX):])
        return f"{conference.short_name if conference else 'Conference'} Tournament"
    names = college.rules.ncaa.round_names
    return f"NCAA {names[round_]}" if 0 <= round_ < len(names) else "NCAA tournament"


def _lower_stage(stage: str, round_: int) -> str:
    """A D-II/D-III fixture's stage (W9e): the regular season or its national tournament's
    round."""
    lower = get_world().defs.college.lower
    if stage == LOWER_REGULAR or lower is None:
        return "Regular season"
    division = lower.divisions.get(int(stage.removeprefix(LOWER_PREFIX) or 0))
    if division is None:
        return "National tournament"
    names = division.tournament.round_names
    return names[round_] if 0 <= round_ < len(names) else "National tournament"


def fixture_out(row: Row[Any], names: dict[int, str], comps: dict[int, Row[Any]],
                firsts: FirstLegs | None = None) -> FixtureOut:
    comp = comps[row.competition_id]
    defs = get_world().defs
    cup = defs.cups.get(comp.key)
    continental = defs.continental.get(comp.key)
    named = (cup.rounds[row.round].name if cup
             else stage_name(continental, row.round) if continental
             else _college_stage(row.stage, row.round) if comp.type == "college"
             else _lower_stage(row.stage, row.round) if comp.type == LOWER_TYPE else None)
    prior = _first_leg_goals(row, firsts or {})
    played = row.status == "played" and row.home_goals is not None and row.away_goals is not None
    agg = ((prior[0] + row.home_goals, prior[1] + row.away_goals)
           if prior and played else (None, None))
    return FixtureOut(
        id=row.id, date=row.date, competition=comp.key, competition_name=comp.name,
        stage=row.stage, round=row.round, tie=row.tie, leg=row.leg,
        home=ClubRef(id=row.home_club_id, name=names[row.home_club_id]),
        away=ClubRef(id=row.away_club_id, name=names[row.away_club_id]),
        neutral=bool(row.neutral), status=row.status, home_goals=row.home_goals,
        away_goals=row.away_goals, extra_time=bool(row.extra_time), home_pens=row.home_pens,
        away_pens=row.away_pens, stage_name=named, agg_home=agg[0], agg_away=agg[1],
        leg1_home=prior[0] if prior else None, leg1_away=prior[1] if prior else None,
    )


def fixtures_out(conn: Connection, rows: Sequence[Row[Any]], names: dict[int, str],
                 comps: dict[int, Row[Any]]) -> list[FixtureOut]:
    """``rows`` as FixtureOut, second legs carrying the aggregate."""
    firsts = first_legs(conn, rows)
    return [fixture_out(r, names, comps, firsts) for r in rows]


def _club_competition(conn: Connection, club_id: int, season_id: int) -> Row[Any] | None:
    return conn.execute(select(competition).join(
        club_league_membership, club_league_membership.c.competition_id == competition.c.id,
    ).where(club_league_membership.c.club_id == club_id,
            club_league_membership.c.season_id == season_id)).first()


def _fold(text_: str) -> str:
    """Lower case without accents, so "Sporting Gijon" finds "Sporting Gijón"."""
    decomposed = unicodedata.normalize("NFKD", text_.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def search_clubs(conn: Connection, q: str, limit: int = 12) -> list[ClubSearchOut]:
    """Clubs whose name contains ``q`` (accents and case ignored; a few letters are enough),
    best matches first: the name starts with it, then a word does, then anywhere in it; ties by
    reputation. Each comes with its country and this season's league."""
    needle = _fold(q).strip()
    if not needle:
        return []
    season_id = read_meta(conn).season_id
    league_of = {r.club_id: r for r in conn.execute(
        select(club_league_membership.c.club_id, competition.c.name, competition.c.key)
        .join(competition, competition.c.id == club_league_membership.c.competition_id)
        .where(club_league_membership.c.season_id == season_id))}
    ranked: list[tuple[int, int, str, Row[Any]]] = []
    for row in conn.execute(select(club.c.id, club.c.name, club.c.reputation,
                                   nation.c.name.label("nation"), nation.c.code.label("code"))
                            .outerjoin(nation, nation.c.id == club.c.nation_id)):
        name = _fold(row.name)
        if needle not in name:
            continue
        rank = 0 if name.startswith(needle) else 1 if f" {needle}" in f" {name}" else 2
        ranked.append((rank, -row.reputation, name, row))
    ranked.sort(key=lambda t: t[:3])
    out = []
    for _, _, _, row in ranked[:limit]:
        league = league_of.get(row.id)
        out.append(ClubSearchOut(id=row.id, name=row.name, nation=row.nation, nation_code=row.code,
                                 competition=league.name if league else None,
                                 competition_key=league.key if league else None))
    return out


def _season_label(conn: Connection, season_id: int) -> str:
    return str(conn.execute(select(season.c.label).where(season.c.id == season_id)).scalar_one())


# --- new career -----------------------------------------------------------------------


def _competition_out(world: World, comp: Row[Any]) -> CompetitionOut:
    league = world.defs.leagues.get(comp.key)
    return CompetitionOut(key=comp.key, name=comp.name, tier=comp.tier or 0,
                          nation=league.nation if league else "")


BIG_FIVE = ("ENG", "ESP", "ITA", "GER", "FRA")  # listed first wherever a country is picked


def _big_five_rank(nation_code: str) -> int:
    return BIG_FIVE.index(nation_code) if nation_code in BIG_FIVE else len(BIG_FIVE)


def world_leagues(base_world: Path, world: World) -> list[LeagueOption]:
    """Every league a career can start in, with its clubs: those the base world was built with,
    and those added since (found by the ratings source's league names, as a new career will)."""
    engine = open_database(base_world)
    try:
        with engine.connect() as conn:
            built = {r.key: r.id for r in conn.execute(select(competition.c.id,
                                                              competition.c.key))}
            result = []
            real_names = load_club_names()  # as the world is built or migrated, for a career
            for key, league in sorted(world.defs.leagues.items(),
                                      key=lambda kv: (_big_five_rank(kv[1].nation),
                                                      kv[1].nation, kv[1].tier)):
                renamed = real_names.get(world.defs.nations[league.nation].name, {})
                if key in built:
                    rows = conn.execute(text("""
                        SELECT c.id, c.name, c.reputation FROM club c
                        JOIN club_league_membership m ON m.club_id = c.id
                        WHERE m.competition_id = :comp AND m.season_id = 1
                    """), {"comp": built[key]}).all()
                elif league.source_leagues:
                    rows = conn.execute(
                        text("SELECT id, name, reputation FROM club WHERE source_league IN :names")
                        .bindparams(bindparam("names", expanding=True)),
                        {"names": league.source_leagues}).all()
                else:
                    continue
                if len(rows) != league.clubs:
                    continue  # as ensure_leagues: a league whose clubs don't add up isn't played
                clubs = [ClubOption(id=r.id, name=renamed.get(r.name, r.name),
                                    reputation=r.reputation,
                                    average_overall=_squad_strength(conn, world, r.id))
                         for r in rows]
                clubs.sort(key=lambda c: -c.average_overall)
                result.append(LeagueOption(key=key, name=league.name, tier=league.tier,
                                           clubs=clubs, nation=league.nation))
            return result
    finally:
        engine.dispose()


def _squad_strength(conn: Connection, world: World, club_id: int) -> float:
    overalls = [ovr for _, ovr in _overalls(conn, world, club_id)]
    best = sorted(overalls, reverse=True)[:16]
    return round(float(np.mean(best)), 1) if best else 0.0


def _overalls(conn: Connection, world: World, club_id: int) -> list[tuple[int, float]]:
    rows = conn.execute(text("""
        SELECT a.*, (SELECT position FROM player_position pp WHERE pp.player_id = a.player_id
                     ORDER BY familiarity DESC LIMIT 1) AS primary_position
        FROM player_attr a JOIN contract k ON k.person_id = a.player_id
        WHERE k.club_id = :club AND k.is_active = 1 AND (k.kind = 'loan' OR NOT EXISTS (
            SELECT 1 FROM contract l WHERE l.person_id = k.person_id AND l.is_active = 1
            AND l.kind = 'loan'))  -- where he plays, as the playing view: this also runs on
                                   -- the base world, which is older than the view
    """), {"club": club_id}).all()
    if not rows:
        return []
    matrix = np.array([[getattr(r, a) for a in ATTRIBUTES] for r in rows], dtype=float)
    groups = world.model.group_overalls(matrix)
    return [(r.player_id, float(groups[world.defs.positions[r.primary_position].group][i]))
            for i, r in enumerate(rows)]


# --- career ---------------------------------------------------------------------------


def career(conn: Connection, world: World, slot: int) -> CareerOut:
    meta = read_meta(conn)
    # A national team's manager without a club: his team is the national team.
    user = meta.user_club_id if meta.user_club_id is not None else meta.user_nation_id
    assert user is not None
    names = _club_names(conn)
    comps = _competitions(conn)
    comp = (_club_competition(conn, meta.user_club_id, meta.season_id)
            if meta.user_club_id is not None else None)
    position = None
    if comp is not None:
        table = standings(conn, world, meta, comp.id, meta.season_id)
        if any(r.played for r in table):
            position = next(r.position for r in table if r.club_id == meta.user_club_id)
    teams = meta.user_teams  # his national team's matches are his too (W8 I5)
    upcoming = conn.execute(select(fixture).where(
        fixture.c.status == "scheduled",
        or_(fixture.c.home_club_id.in_(teams), fixture.c.away_club_id.in_(teams)),
    ).order_by(fixture.c.date, fixture.c.id)).first()
    recent = conn.execute(select(fixture).where(
        fixture.c.status == "played",
        or_(fixture.c.home_club_id == user, fixture.c.away_club_id == user),
    ).order_by(fixture.c.date.desc()).limit(5)).all()
    college = _college_career(conn, world, meta)
    if college is not None:
        position = college[1]
    return CareerOut(
        slot=slot, date=meta.current_date.isoformat(), season=_season_label(conn, meta.season_id),
        season_end=season_calendar(world, meta, meta.season_id).season_end.isoformat(),
        manager=meta.manager_name, club=ClubRef(id=user, name=names[user]),
        competition=_competition_out(world, comp) if comp else None,
        position=position,
        next_fixture=fixtures_out(conn, [upcoming], names, comps)[0] if upcoming else None,
        recent=fixtures_out(conn, recent, names, comps),
        currency=meta.currency,
        college=college[0] if college else None,
        nation=(ClubRef(id=meta.user_nation_id, name=names[meta.user_nation_id])
                if meta.user_nation_id is not None else None),
        nation_only=meta.user_club_id is None,
    )


def _college_career(conn: Connection, world: World, meta: CareerMeta
                    ) -> tuple[CollegeCareerOut, int | None] | None:
    """A college coach's program, and its place in its conference's table (once played)."""
    row = conn.execute(select(college_team).where(
        college_team.c.club_id == meta.user_club_id)).first()
    if row is None:
        return None
    conference = world.defs.college.conferences[str(row.conference)]
    table = conference_tables(conn, world, meta, meta.season_id).get(str(row.conference), [])
    position = None
    if any(r.played for r in table):
        position = next((r.position for r in table if r.club_id == meta.user_club_id), None)
    rpi = rankings(conn, world, meta.season_id)
    rank = None
    if meta.user_club_id in rpi:
        order = sorted(rpi, key=lambda c: (-rpi[c], c))
        rank = order.index(meta.user_club_id) + 1
    prestige = float(row.prestige) if row.prestige is not None else float(
        world.defs.college.recruiting.programs.prestige_by_tier[int(row.tier)])
    bonus = facilities_bonus(conn, world, int(meta.user_club_id or 0))
    return CollegeCareerOut(conference=str(row.conference), conference_name=conference.name,
                            tier=int(row.tier), prestige=round(prestige + bonus),
                            prestige_facilities=round(bonus), rpi_rank=rank,
                            mode=meta.college_mode), position


def competitions(conn: Connection, world: World) -> list[CompetitionOut]:
    return [CompetitionOut(key=a.league.key, name=a.league.name, tier=a.league.tier,
                           nation=a.league.nation)
            for a in active_leagues(conn, world)]


SEASON_VIEW = "season"  # a phased league's whole-season (annual) table


def _current_phase(conn: Connection, league: LeagueDef, competition_id: int,
                   season_id: int) -> str:
    """The phase to show by default: the first whose league matches aren't all played, else
    the last."""
    for phase in league.phases:
        first, last = phase_rounds(conn, league, competition_id, season_id, phase.key)
        left = conn.execute(select(func.count()).select_from(fixture).where(
            fixture.c.competition_id == competition_id, fixture.c.season_id == season_id,
            fixture.c.stage == "league", fixture.c.status == "scheduled",
            fixture.c.round.between(first, last))).scalar_one()
        if left:
            return phase.key
    return league.phases[-1].key


def table(conn: Connection, world: World, key: str, season_id: int | None = None,
          phase: str | None = None) -> TableOut:
    """A league's table: the season's, or (a league of phases) a phase's, by default the one
    under way. A league of conferences or zones also gets each group's table."""
    meta = read_meta(conn)
    season_id = season_id or meta.season_id
    comp = conn.execute(select(competition).where(competition.c.key == key)).one()
    league = world.defs.leagues[key]
    if league.phases and phase is None:
        phase = _current_phase(conn, league, comp.id, season_id)
    shown = None if phase in (None, SEASON_VIEW) or not league.phases else phase
    if shown is not None and shown not in {p.key for p in league.phases}:
        shown = league.phases[0].key
    zones: dict[int, str] = {}  # by league position
    group_zones: dict[tuple[str, int], str] = {}
    for mv in league.movements:
        zone = "promotion" if mv.kind is MovementKind.PROMOTION else "relegation"
        for pos in range(mv.ranks[0], mv.ranks[1] + 1):
            zones[pos] = zone
    for playoff in league.playoffs:
        if playoff.phase != shown:
            continue
        for pos in playoff.entrant_ranks():
            zones[pos] = "playoff"
        for group_rank in playoff.group_ranks():
            group_zones[group_rank] = "playoff"
    if league.tier == 1 and not league.phases and league.title_playoff is None:
        zones.setdefault(1, "champion")
    names = _club_names(conn)
    form = _form(conn, comp.id, season_id)
    ordered = standings(conn, world, meta, comp.id, season_id, shown)
    if not any(r.played for r in ordered):  # pre-season: alphabetical, like the real thing
        ordered.sort(key=lambda r: names[r.club_id])
        for position, r in enumerate(ordered, start=1):
            r.position = position
    outcomes = {} if shown is not None else {
        r.club_id: r.outcome for r in conn.execute(select(league_final).where(
            league_final.c.season_id == season_id, league_final.c.competition_id == comp.id))}
    places = (_europe_places(conn, world, league, season_id)
              if league.tier == 1 and shown is None else [])
    by_rank = {rank: (p.competition, "league_phase" if p.round == "LP" else "qualifying")
               for p in places if p.positions
               for rank in range(p.positions[0], p.positions[1] + 1)}
    went = _went_to_europe(conn, world, season_id, [r.club_id for r in ordered]) if (
        places and outcomes) else {}

    def europe_mark(club_id: int, position: int) -> tuple[str | None, str | None]:
        if went:
            return went.get(club_id, (None, None))
        return by_rank.get(position, (None, None))

    def row_out(r: TableRow, zone: str | None) -> TableRowOut:
        return TableRowOut(
            position=r.position, club=ClubRef(id=r.club_id, name=names[r.club_id]),
            played=r.played, won=r.won, drawn=r.drawn, lost=r.lost, goals_for=r.goals_for,
            goals_against=r.goals_against, goal_difference=r.goal_difference, points=r.points,
            zone=zone, form=form.get(r.club_id, []),
            outcome=outcomes.get(r.club_id),
            europe=europe_mark(r.club_id, r.position)[0],
            europe_stage=europe_mark(r.club_id, r.position)[1],
        )

    rows = [row_out(r, zones.get(r.position)) for r in ordered]
    groups: list[GroupTableOut] = []
    if league.groups and any(r.played for r in ordered):
        members = league_groups(conn, league, [r.club_id for r in ordered])
        for g in league.groups:
            groups.append(GroupTableOut(key=g.key, name=g.name, rows=[
                row_out(r, group_zones.get((g.key, r.position)))
                for r in group_table(ordered, members[g.key])]))
    elif league.groups:  # pre-season: each group alphabetical
        members = league_groups(conn, league, [r.club_id for r in ordered])
        for g in league.groups:
            mine = sorted(members[g.key], key=lambda c: names[c])
            by_club = {r.club_id: r for r in ordered}
            groups.append(GroupTableOut(key=g.key, name=g.name, rows=[
                row_out(TableRow(**{**vars(by_club[c]), "position": k}), None)
                for k, c in enumerate(mine, start=1)]))
    titles = [TitleOut(title=t.title, club=ClubRef(id=t.club_id, name=names[t.club_id]),
                       kind=t.kind, phase=t.phase)
              for t in conn.execute(select(league_title).where(
                  league_title.c.season_id == season_id,
                  league_title.c.competition_id == comp.id).order_by(league_title.c.won_on))]
    first_match = conn.execute(select(func.min(fixture.c.date)).where(
        fixture.c.competition_id == comp.id, fixture.c.season_id == season_id,
        fixture.c.stage == "league")).scalar()
    return TableOut(competition=key, name=comp.name, season=_season_label(conn, season_id),
                    final=bool(outcomes) if shown is None else _phase_done(
                        conn, league, comp.id, season_id, shown),
                    started=any(r.played for r in ordered),
                    first_match=first_match, rows=rows,
                    phases=([TableViewOut(key=p.key, name=p.name) for p in league.phases]
                            + [TableViewOut(key=SEASON_VIEW, name="Season")]
                            if league.phases else []),
                    phase=(shown or SEASON_VIEW) if league.phases else None,
                    groups=groups, titles=titles,
                    europe_places=[EuropePlaceOut(
                        competition=p.competition,
                        name=world.defs.continental[p.competition].short_name,
                        stage="league_phase" if p.round == "LP" else "qualifying",
                        how=_place_how(world, p), round=p.round,
                        round_name=_round_words(world, p)) for p in places],
                    europe_actual=bool(went))


def _phase_done(conn: Connection, league: LeagueDef, competition_id: int, season_id: int,
                phase: str) -> bool:
    first, last = phase_rounds(conn, league, competition_id, season_id, phase)
    rows = conn.execute(select(fixture.c.status).where(
        fixture.c.competition_id == competition_id, fixture.c.season_id == season_id,
        fixture.c.stage == "league", fixture.c.round.between(first, last))).all()
    return bool(rows) and all(r.status == "played" for r in rows)


def league_playoffs(conn: Connection, world: World, key: str, season_id: int | None = None
                    ) -> list[LeaguePlayoffOut]:
    """A league's play-offs for a season, as cup rounds: drawn rounds with their ties and
    matches (a series' games as one tie), rounds to come with their dates."""
    meta = read_meta(conn)
    season_id = season_id or meta.season_id
    league = world.defs.leagues[key]
    if not league.playoffs:
        return []
    names = _club_names(conn)
    comps = _competitions(conn)
    comp_id = next(cid for cid, r in comps.items() if r.key == key)
    calendar = league_calendar(world, league, season_id)

    def ref(club_id: int | None) -> ClubRef | None:
        return ClubRef(id=club_id, name=names[club_id]) if club_id else None

    out = []
    for playoff in league.playoffs:
        dated = calendar.competitions[league.calendar_key(playoff.phase)]
        days = playoff_dates(dated.end, dated.playoffs_end, playoff.rounds)
        ties = conn.execute(select(playoff_tie).where(
            playoff_tie.c.season_id == season_id, playoff_tie.c.playoff_key == playoff.key)
            .order_by(playoff_tie.c.round, playoff_tie.c.id)).all()
        rows = conn.execute(select(fixture).where(
            fixture.c.season_id == season_id, fixture.c.competition_id == comp_id,
            fixture.c.stage == playoff.key).order_by(fixture.c.date, fixture.c.leg)).all()
        games: dict[tuple[int, str], list[FixtureOut]] = defaultdict(list)
        for row, f in zip(rows, fixtures_out(conn, rows, names, comps), strict=True):
            games[(row.round, (row.tie or "").split(":")[0])].append(f)
        rounds = []
        for index, rnd in enumerate(playoff.rounds):
            in_round = [t for t in ties if t.round == index]
            rounds.append(CupRoundOut(
                index=index, name=rnd.name, dates=[d.isoformat() for d in days[index]],
                legs=rnd.legs, games=rnd.games, drawn=bool(in_round),
                ties=[CupTieOut(tie=t.tie, home=ClubRef(id=t.club_a_id, name=names[t.club_a_id]),
                                away=ref(t.club_b_id), fixtures=games.get((index, t.tie), []),
                                winner=ref(t.winner_club_id)) for t in in_round]))
        final = [t for t in ties if t.round == len(playoff.rounds) - 1]
        out.append(LeaguePlayoffOut(key=playoff.key, name=playoff.name, phase=playoff.phase,
                                    title=playoff.title, rounds=rounds,
                                    winner=ref(final[0].winner_club_id) if final else None))
    return out


def _europe_places(conn: Connection, world: World, league: LeagueDef, season_id: int
                   ) -> list[CountryPlace]:
    """A top league's European places for the season after ``season_id`` (what its table
    earns), when the game has the European competitions."""
    on = world.defs.europe.enabled or conn.execute(
        select(continental_entry.c.id)).first() is not None
    return country_places(conn, world, league.nation, season_id + 1) if on else []


def _place_how(world: World, place: CountryPlace) -> str:
    if place.cup is not None:
        cup = world.defs.cups.get(place.cup)
        return f"{cup.name if cup else 'Cup'} winners"
    assert place.positions is not None
    first, last = place.positions
    how = ordinal(first) if first == last else f"{ordinal(first)}–{ordinal(last)}"
    return f"{how} (European Performance Spot)" if place.performance_spot else how


def _round_words(world: World, place: CountryPlace) -> str:
    """Where a place enters, in words: "League phase", "Second qualifying round (Champions
    Path)"."""
    if place.round == "LP":
        return "League phase"
    return round_name(world, Node(place.competition, place.round, place.path))


def _went_to_europe(conn: Connection, world: World, season_id: int, clubs: list[int]
                    ) -> dict[int, tuple[str, str]]:
    """Where a finished season's clubs went in Europe the season after (once its entries are
    made): the competition and stage they qualified for. A club that lost its play-off round
    shows that round, not the competition it dropped into."""
    keys = {r.id: r.key for r in conn.execute(select(competition.c.id, competition.c.key))}
    went: dict[int, tuple[str, str]] = {}
    for e in conn.execute(select(continental_entry).where(
            continental_entry.c.season_id == season_id + 1,
            continental_entry.c.club_id.in_(clubs))):
        kind, _, origin = e.route.partition(":")
        if e.entered:  # where it started (W7)
            start = node_of(e.entered)
            went[e.club_id] = (start.competition, "league_phase" if start.round == "LP"
                               else "qualifying")
        elif kind == "dropped" and origin in world.defs.continental:
            went[e.club_id] = (origin, "qualifying")
        else:
            went[e.club_id] = (keys[e.competition_id], e.stage)
    return went


def seasons(conn: Connection) -> list[SeasonOut]:
    current = read_meta(conn).season_id
    finished = {r.season_id for r in conn.execute(select(league_final.c.season_id).distinct())}
    return [SeasonOut(id=r.id, label=r.label, current=r.id == current, finished=r.id in finished)
            for r in conn.execute(select(season).order_by(season.c.id.desc()))]


def _cup_run(world: World, key: str, name: str, club_id: int, ties: list[Row[Any]]
             ) -> CupRunOut | None:
    """How far ``club_id`` went in one cup's season, from its ties (byes included)."""
    mine = [t for t in ties if club_id in (t.club_a_id, t.club_b_id)]
    if not mine:
        return None
    last = max(mine, key=lambda t: t.round)
    rounds = world.defs.cups[key].rounds
    won = last.round == len(rounds) - 1 and last.winner_club_id == club_id
    out = last.winner_club_id is not None and last.winner_club_id != club_id
    through = last.winner_club_id == club_id and last.round + 1 < len(rounds)
    reached = "Winners" if won else rounds[last.round + 1 if through else last.round].name
    return CupRunOut(key=key, name=name, reached=reached, won=won, out=out)


def cup_runs(conn: Connection, world: World, club_id: int) -> dict[int, list[CupRunOut]]:
    """Every season's cup runs of a club."""
    comps = {r.id: r for r in conn.execute(select(competition).where(competition.c.type == "cup"))}
    ties = conn.execute(select(cup_tie).where(or_(
        cup_tie.c.club_a_id == club_id, cup_tie.c.club_b_id == club_id))).all()
    by_cup: dict[tuple[int, int], list[Row[Any]]] = defaultdict(list)
    for t in ties:
        by_cup[(t.season_id, t.competition_id)].append(t)
    runs: dict[int, list[CupRunOut]] = defaultdict(list)
    for (season_id, comp_id), cup_ties in sorted(by_cup.items()):
        comp = comps.get(comp_id)  # the domestic cups' ties only, not the European ones
        if comp is not None and comp.key in world.defs.cups:
            run = _cup_run(world, comp.key, comp.name, club_id, cup_ties)
            if run is not None:
                runs[season_id].append(run)
    return runs


def cups(conn: Connection, world: World) -> list[CupSummaryOut]:
    """This season's cups, every country's: the round under way, and how the user's club is
    doing. Each carries its nation, for the page to choose by."""
    meta = read_meta(conn)
    names = _club_names(conn)
    ids = {r.key: r.id for r in conn.execute(select(competition.c.id, competition.c.key))}
    playing = {cup.key for cup, _ in cups_in_play(conn, world, meta.season_id)}
    result = []
    for cup, calendar in season_cups(world, meta.season_id):
        ties = (conn.execute(select(cup_tie).where(
            cup_tie.c.season_id == meta.season_id, cup_tie.c.competition_id == ids[cup.key]))
            .all() if cup.key in ids else [])
        winner = next((t.winner_club_id for t in ties
                       if t.round == len(cup.rounds) - 1 and t.winner_club_id), None)
        current = None
        if ties and winner is None:
            latest = max(t.round for t in ties)
            done = all(t.winner_club_id for t in ties if t.round == latest)
            current = cup.rounds[latest + 1 if done else latest].name
        status = None
        if meta.user_club_id is not None and ties:
            run = _cup_run(world, cup.key, cup.name, meta.user_club_id, list(ties))
            if run is None:
                status = "Not in it yet"
            elif run.won:
                status = "Winners"
            else:
                status = f"{'Out in' if run.out else 'In'} the {run.reached.lower()}"
        elif not ties:
            first = calendar.cups[cup.key][0][0]
            status = ("The draw is still to come"
                      if cup.key in playing and meta.current_date < first
                      else "Starts next season")
        result.append(CupSummaryOut(
            key=cup.key, name=cup.name, nation=cup.nation, current_round=current,
            user_status=status,
            winner=ClubRef(id=winner, name=names[winner]) if winner else None))
    return result


def cup(conn: Connection, world: World, key: str, season_id: int | None = None) -> CupOut:
    """A cup's season: every round, drawn or still to come, with its ties and results."""
    meta = read_meta(conn)
    season_id = season_id or meta.season_id
    definition = world.defs.cups[key]
    dated: list[list[date]] = next(
        (calendar.cups[key] for cup, calendar in season_cups(world, season_id) if cup.key == key),
        [[] for _ in definition.rounds])
    names = _club_names(conn)
    comps = _competitions(conn)
    comp_id = next((cid for cid, r in comps.items() if r.key == key), None)
    ties = conn.execute(select(cup_tie).where(
        cup_tie.c.season_id == season_id, cup_tie.c.competition_id == comp_id,
    ).order_by(cup_tie.c.round, cup_tie.c.id)).all() if comp_id is not None else []
    games: dict[tuple[int, str], list[FixtureOut]] = defaultdict(list)
    if comp_id is not None:
        rows = conn.execute(select(fixture).where(
            fixture.c.season_id == season_id, fixture.c.competition_id == comp_id,
        ).order_by(fixture.c.leg)).all()
        for row, out in zip(rows, fixtures_out(conn, rows, names, comps), strict=True):
            games[(row.round, row.tie)].append(out)

    def ref(club_id: int | None) -> ClubRef | None:
        return ClubRef(id=club_id, name=names[club_id]) if club_id else None

    rounds = []
    for index, rnd in enumerate(definition.rounds):
        in_round = [t for t in ties if t.round == index]
        rounds.append(CupRoundOut(
            index=index, name=rnd.name,
            dates=[d.isoformat() for d in dated[index]],
            legs=rnd.legs, drawn=bool(in_round),
            ties=[CupTieOut(tie=t.tie, home=ClubRef(id=t.club_a_id, name=names[t.club_a_id]),
                            away=ref(t.club_b_id), fixtures=games.get((index, t.tie), []),
                            winner=ref(t.winner_club_id)) for t in in_round]))
    final = [t for t in ties if t.round == len(definition.rounds) - 1]
    return CupOut(key=key, name=definition.name, nation=definition.nation,
                  season=_season_label(conn, season_id), rounds=rounds,
                  winner=ref(final[0].winner_club_id) if final else None)


def club_history(conn: Connection, world: World, club_id: int) -> ClubHistoryOut:
    """Every league season of a club in this career, newest first: final positions, and the
    season in progress so far."""
    require_club(conn, club_id)
    meta = read_meta(conn)
    names = _club_names(conn)
    comps = _competitions(conn)
    labels = {r.id: r.label for r in conn.execute(select(season))}
    managed = club_id == meta.user_club_id
    top_europe = next((c.key for c in competitions_by_rank(world)), None)

    def competition_of(comp_id: int) -> CompetitionOut:
        return _competition_out(world, comps[comp_id])

    runs = cup_runs(conn, world, club_id)
    europe = european_runs(conn, world, club_id)
    trebles = {sid: found for sid, season_runs in europe.items()
               if any(r.won and r.key == top_europe for r in season_runs)
               and (found := treble(conn, world, sid)) is not None and found.club_id == club_id}
    rows: list[ClubSeasonOut] = []
    finals = conn.execute(select(league_final).where(league_final.c.club_id == club_id)
                          .order_by(league_final.c.season_id.desc())).all()
    finished = {f.season_id for f in finals}
    current = _club_competition(conn, club_id, meta.season_id)
    if current is not None and meta.season_id not in finished:
        table_rows = standings(conn, world, meta, current.id, meta.season_id)
        mine = next(r for r in table_rows if r.club_id == club_id)
        rows.append(ClubSeasonOut(
            season_id=meta.season_id, season=labels[meta.season_id],
            competition=competition_of(current.id),
            position=mine.position if any(r.played for r in table_rows) else None,
            played=mine.played, won=mine.won, drawn=mine.drawn, lost=mine.lost,
            goals_for=mine.goals_for, goals_against=mine.goals_against, points=mine.points,
            outcome=None, final=False, managed=managed, cups=runs.get(meta.season_id, []),
            europe=europe.get(meta.season_id, [])))
    for f in finals:
        rows.append(ClubSeasonOut(
            season_id=f.season_id, season=labels[f.season_id],
            competition=competition_of(f.competition_id), position=f.position,
            played=f.played, won=f.won, drawn=f.drawn, lost=f.lost, goals_for=f.goals_for,
            goals_against=f.goals_against, points=f.points, outcome=f.outcome, final=True,
            managed=managed, cups=runs.get(f.season_id, []), europe=europe.get(f.season_id, []),
            treble=f.season_id in trebles,
            treble_trophies=trebles[f.season_id].trophies if f.season_id in trebles else []))

    def promoted(f: Row[Any]) -> bool:  # a lower league's champions go up too
        return f.outcome in ("promoted", "playoff_winner") or (
            f.outcome == "champion" and (comps[f.competition_id].tier or 1) > 1)

    won = conn.execute(select(league_title).where(league_title.c.club_id == club_id)
                       .order_by(league_title.c.season_id, league_title.c.won_on)).all()

    def title_key(t: Row[Any]) -> str:  # a league's own title by its key; its others apart
        key = comps[t.competition_id].key
        return key if t.title == comps[t.competition_id].name else f"{key}|{t.title}"

    return ClubHistoryOut(
        club=ClubRef(id=club_id, name=names[club_id]), seasons=rows,
        titles=sum(t.kind == "champion" for t in won),
        promotions=sum(promoted(f) for f in finals),
        relegations=sum(f.outcome == "relegated" for f in finals),
        trophies=trophy_cabinet(
            world, labels, [(t.season_id, title_key(t), t.title) for t in won], runs, europe,
            world_titles(conn, club_id)),
        treble_seasons=[r.season for r in reversed(rows) if r.treble],
        european_titles=sum(run.won for season_runs in europe.values() for run in season_runs),
    )


def _form(conn: Connection, competition_id: int, season_id: int) -> dict[int, list[str]]:
    rows = conn.execute(select(fixture).where(
        fixture.c.competition_id == competition_id, fixture.c.season_id == season_id,
        fixture.c.stage == "league", fixture.c.status == "played",
    ).order_by(fixture.c.date)).all()
    form: dict[int, list[str]] = defaultdict(list)
    for r in rows:
        for club_id, scored, conceded in ((r.home_club_id, r.home_goals, r.away_goals),
                                          (r.away_club_id, r.away_goals, r.home_goals)):
            form[club_id].append("W" if scored > conceded else "D" if scored == conceded else "L")
    return {c: results[-5:] for c, results in form.items()}


def fixtures(conn: Connection, *, club_id: int | None = None, competition_key: str | None = None,
             season_id: int | None = None) -> list[FixtureOut]:
    meta = read_meta(conn)
    query = select(fixture).where(fixture.c.season_id == (season_id or meta.season_id))
    if club_id is not None:
        query = query.where(or_(fixture.c.home_club_id == club_id,
                                fixture.c.away_club_id == club_id))
    if competition_key is not None:
        comp_id: int = conn.execute(select(competition.c.id).where(
            competition.c.key == competition_key)).scalar_one()
        query = query.where(fixture.c.competition_id == comp_id)
    names = _club_names(conn)
    comps = _competitions(conn)
    rows = conn.execute(query.order_by(fixture.c.date, fixture.c.id)).all()
    return fixtures_out(conn, rows, names, comps)


# --- players --------------------------------------------------------------------------

_PLAYER_SQL = """
    SELECT p.id, p.first_name, p.last_name, p.known_as, p.birth_date, n.name AS nation,
           pl.height_cm, pl.weight_kg, pl.preferred_foot, pl.weak_foot, pl.skill_moves,
           pl.pa_hidden, pl.value_eur_cents, k.club_id, k.wage_weekly_cents, k.end_date,
           s.condition, s.form, s.injured_until, s.injury, s.suspended_matches, d.trend,
           pl.retired_on, c.reputation AS club_reputation, pl.reputation AS player_reputation,
           pl.value_premium, k.kind AS contract_kind, o.club_id AS owner_club_id
    FROM person p
    JOIN player pl ON pl.person_id = p.id
    LEFT JOIN nation n ON n.id = p.nation_id
    LEFT JOIN playing k ON k.person_id = p.id
    LEFT JOIN contract o ON o.person_id = p.id AND o.is_active = 1 AND o.kind != 'loan'
    LEFT JOIN club c ON c.id = o.club_id
    LEFT JOIN player_state s ON s.player_id = p.id
    LEFT JOIN player_development d ON d.player_id = p.id
"""


def _player_rows(conn: Connection, where: str, params: dict[str, Any]) -> list[Row[Any]]:
    return list(conn.execute(text(_PLAYER_SQL + " WHERE " + where), params).all())


def _attributes(conn: Connection, ids: list[int]) -> dict[int, np.ndarray]:
    return {r.player_id: np.array([getattr(r, a) for a in ATTRIBUTES], dtype=float)
            for r in conn.execute(select(player_attr).where(player_attr.c.player_id.in_(ids)))}


def _positions(conn: Connection, ids: list[int]) -> dict[int, dict[str, int]]:
    result: dict[int, dict[str, int]] = defaultdict(dict)
    for r in conn.execute(select(player_position).where(player_position.c.player_id.in_(ids))):
        result[r.player_id][r.position] = r.familiarity
    return result


def _season_stats(conn: Connection, ids: list[int], season_id: int) -> dict[int, Row[Any]]:
    if not ids:
        return {}
    query = text("""
        SELECT pm.player_id, COUNT(*) AS apps, SUM(pm.goals) AS goals, SUM(pm.assists) AS assists,
               AVG(pm.rating) AS rating
        FROM player_match pm JOIN fixture f ON f.id = pm.fixture_id
        WHERE f.season_id = :season AND pm.player_id IN :ids
        GROUP BY pm.player_id
    """).bindparams(bindparam("ids", expanding=True))
    rows = conn.execute(query, {"season": season_id, "ids": ids}).all()
    return {r.player_id: r for r in rows}


def _season_start_overalls(conn: Connection, ids: list[int], season_id: int) -> dict[int, int]:
    """Each player's overall as ``season_id`` began (world/overall_history.py); players with no
    record (youth who joined part-way through, a save from before the record) are left out."""
    if not ids:
        return {}
    return {r.player_id: r.overall for r in conn.execute(select(player_season_overall).where(
        player_season_overall.c.season_id == season_id,
        player_season_overall.c.player_id.in_(ids)))}


def _squad_entry(world: World, r: Row[Any], attrs: np.ndarray, fams: dict[str, int],
                 stats: Row[Any] | None, day: date, season_start: int | None = None, *,
                 currency: str) -> SquadPlayerOut:
    primary = max(fams, key=lambda pos: fams[pos]) if fams else "CM"
    overall = float(world.model.group_overalls(attrs)[world.defs.positions[primary].group])
    age = age_on(date.fromisoformat(r.birth_date), day)
    injured = r.injured_until if r.injured_until and r.injured_until > day.isoformat() else None
    # A free agent is priced at his own reputation, not his old club's (he carries it with him).
    value = value_eur(world.defs.valuation, round(overall), years_old(r.birth_date, day),
                      primary == "GK",
                      r.club_reputation if r.club_reputation is not None else r.player_reputation,
                      r.value_premium or 0.0)
    shown = world.defs.development.trend_shown
    trend = r.trend or 0.0
    return SquadPlayerOut(
        id=r.id, name=display_name(r.first_name, r.last_name, r.known_as),
        short_name=short_name(r.first_name, r.last_name, r.known_as), position=primary,
        positions=[p for p, f in sorted(fams.items(), key=lambda kv: -kv[1]) if f >= 15],
        age=age, nationality=r.nation, overall=round(overall),
        trend=1 if trend >= shown else -1 if trend <= -shown else 0,
        season_start_overall=season_start,
        condition=round(r.condition if r.condition is not None else 100),
        form=round(r.form if r.form is not None else 6.5, 1), injury=r.injury if injured else None,
        injured_until=injured, suspended=r.suspended_matches or 0,
        value_eur=quote(value, world, currency),
        wage_weekly_eur=(r.wage_weekly_cents or 0) // 100, contract_end=r.end_date or "",
        height_cm=r.height_cm, preferred_foot=r.preferred_foot,
        appearances=stats.apps if stats else 0, goals=stats.goals or 0 if stats else 0,
        assists=stats.assists or 0 if stats else 0,
        average_rating=round(stats.rating, 2) if stats else None,
    )


def squad(conn: Connection, world: World, club_id: int) -> list[SquadPlayerOut]:
    meta = read_meta(conn)
    # A national team's players are its called-up squad (world/international).
    where = ("p.id IN (SELECT player_id FROM national_squad WHERE club_id = :club)"
             if is_national(conn, club_id) else "k.club_id = :club")
    rows = _player_rows(conn, where, {"club": club_id})
    ids = [r.id for r in rows]
    attrs, positions = _attributes(conn, ids), _positions(conn, ids)
    stats = _season_stats(conn, ids, meta.season_id)
    started = _season_start_overalls(conn, ids, meta.season_id)
    order = list(world.defs.positions)
    entries = [_squad_entry(world, r, attrs[r.id], positions[r.id], stats.get(r.id),
                            meta.current_date, started.get(r.id), currency=meta.currency)
               for r in rows]
    college = _college_players(conn, meta, ids)
    for e in entries:
        e.college = college.get(e.id)
    return sorted(entries, key=lambda e: (order.index(e.position), -e.overall))


def _college_players(conn: Connection, meta: CareerMeta, ids: list[int]
                     ) -> dict[int, CollegePlayerOut]:
    """Each college player among ``ids``: his class, scholarship and draft status."""
    if not ids:
        return {}
    start = int(conn.execute(select(season.c.start_date).where(
        season.c.id == meta.season_id)).scalar_one()[:4])
    found = {}
    for r in conn.execute(select(college_player).where(
            college_player.c.player_id.in_(ids),
            college_player.c.status.in_(("enrolled", "prospect")))):
        year = min(4, int(r.class_year))
        last = start + (4 - year)  # the autumn of his last season
        found[int(r.player_id)] = CollegePlayerOut(
            class_year=CLASS_NAMES[year], scholarship=round(float(r.scholarship), 2),
            declared=r.status == "prospect", leaves=f"{last}-{str(last + 1)[2:]}")
    return found


# --- other clubs ----------------------------------------------------------------------


class ClubNotFound(LookupError):
    pass


def require_club(conn: Connection, club_id: int) -> None:
    if conn.execute(select(club.c.id).where(club.c.id == club_id)).first() is None:
        raise ClubNotFound(club_id)


def _rough(value: float) -> int:
    """Two significant figures: what another club's accounts reveal from the outside."""
    if value <= 0:
        return 0
    digits = int(np.floor(np.log10(value))) - 1
    return int(round(value, -digits))


def _status(entry: SquadPlayerOut) -> str:
    if entry.injury:
        return "injured"
    return "suspended" if entry.suspended else "available"


def _outside_view(entry: SquadPlayerOut) -> ClubPlayerOut:
    return ClubPlayerOut(
        id=entry.id, name=entry.name, position=entry.position, positions=entry.positions,
        age=entry.age, nationality=entry.nationality, overall=entry.overall, trend=entry.trend,
        status=_status(entry), value_eur=entry.value_eur, contract_end=entry.contract_end,
        form=entry.form, appearances=entry.appearances, goals=entry.goals,
    )


def club_players(conn: Connection, world: World, club_id: int) -> list[ClubPlayerOut]:
    """Any club's squad as another club sees it (the user's own squad page shows more)."""
    require_club(conn, club_id)
    return [_outside_view(e) for e in squad(conn, world, club_id)]


def club_overview(conn: Connection, world: World, club_id: int) -> ClubOverviewOut:
    """A club's profile. Money is rounded for clubs other than the user's own."""
    meta = read_meta(conn)
    row = conn.execute(
        select(club, nation.c.name.label("nation_name"))
        .outerjoin(nation, nation.c.id == club.c.nation_id)
        .where(club.c.id == club_id)).first()
    if row is None:
        raise ClubNotFound(club_id)
    names = _club_names(conn)
    comps = _competitions(conn)
    comp = _club_competition(conn, club_id, meta.season_id)
    position = points = None
    played = 0
    if comp is not None:
        table = standings(conn, world, meta, comp.id, meta.season_id)
        mine = next((r for r in table if r.club_id == club_id), None)
        if mine is not None and any(r.played for r in table):
            position, points, played = mine.position, mine.points, mine.played
    players = squad(conn, world, club_id)
    wage_bill = sum(p.wage_weekly_eur for p in players)
    money = conn.execute(select(club_finance.c.transfer_budget_cents,
                                club_finance.c.balance_cents)
                         .where(club_finance.c.club_id == club_id)).first()
    involved = or_(fixture.c.home_club_id == club_id, fixture.c.away_club_id == club_id)
    recent = conn.execute(select(fixture).where(fixture.c.status == "played", involved)
                          .order_by(fixture.c.date.desc(), fixture.c.id.desc()).limit(5)).all()
    upcoming = conn.execute(select(fixture).where(fixture.c.status == "scheduled", involved)
                            .order_by(fixture.c.date, fixture.c.id).limit(5)).all()
    own = club_id == meta.user_club_id
    budget = money.transfer_budget_cents / 100 if money else 0.0
    balance = money.balance_cents / 100 if money else 0.0
    if not own:  # what another club's accounts reveal from the outside
        wage_bill, budget = _rough(wage_bill), _rough(budget)
        balance = _rough(balance) if balance >= 0 else -_rough(-balance)
    team = conn.execute(text("SELECT code, confederation, elo, (SELECT COUNT(*) FROM "
                             "national_team o WHERE o.elo > t.elo) + 1 AS rank FROM "
                             "national_team t WHERE club_id = :c"), {"c": club_id}).first()
    return ClubOverviewOut(
        national=NationalTeamOut(code=team.code, confederation=team.confederation,
                                 elo=round(team.elo), rank=team.rank) if team else None,
        club=ClubRef(id=club_id, name=row.name), own_club=own, nation=row.nation_name,
        competition=_competition_out(world, comp) if comp else None,
        position=position, points=points, played=played, reputation=row.reputation,
        stadium_name=row.stadium_name, stadium_capacity=row.stadium_capacity,
        manager=meta.manager_name if own else None,
        wage_bill_weekly_eur=int(wage_bill), budget_eur=int(budget),
        balance_eur=int(balance),
        squad_size=len(players),
        average_age=round(float(np.mean([p.age for p in players])), 1) if players else 0.0,
        average_overall=round(float(np.mean([p.overall for p in players])), 1) if players else 0.0,
        top_players=[_outside_view(p) for p in sorted(players, key=lambda p: -p.overall)[:5]],
        recent=fixtures_out(conn, recent, names, comps),
        upcoming=fixtures_out(conn, upcoming, names, comps),
        recent_transfers=_recent_transfers(conn, world, club_id, names, meta.currency),
        college=college_season_record(conn, world, meta, club_id, meta.season_id),
    )


def college_season_record(conn: Connection, world: World, meta: CareerMeta, club_id: int,
                          season_id: int) -> CollegeSeasonRecordOut | None:
    """A college program's season, for its club page and the season summary."""
    from footsim.world.college.season import conference_tables, team_season

    ts = team_season(conn, world, meta, club_id, season_id)
    if ts is None:
        return _lower_season_record(conn, world, meta, club_id, season_id)
    team = conn.execute(select(college_team.c.tier, college_team.c.prestige).where(
        college_team.c.club_id == club_id)).one()
    conf = world.defs.college.conferences[ts.conference]
    label = conn.execute(select(season.c.label).where(season.c.id == season_id)).scalar()
    bonus = facilities_bonus(conn, world, club_id)
    row = ts.row
    return CollegeSeasonRecordOut(
        season=str(label or ""), conference=conf.short_name, conference_name=conf.name,
        conference_position=row.position if row else None,
        conference_teams=len(conference_tables(conn, world, meta, season_id).get(
            ts.conference, [])),
        conference_won=row.won if row else 0, conference_drawn=row.drawn if row else 0,
        conference_lost=row.lost if row else 0, conference_points=row.points if row else 0,
        won=ts.overall.won, drawn=ts.overall.drawn, lost=ts.overall.lost,
        goals_for=ts.overall.goals_for, goals_against=ts.overall.goals_against,
        rpi_rank=ts.rpi_rank, ncaa=ts.ncaa, titles=ts.titles, tier=int(team.tier),
        prestige=round(float(team.prestige or 0.0) + bonus, 1),
        prestige_facilities=round(bonus, 1))



def _lower_season_record(conn: Connection, world: World, meta: CareerMeta, club_id: int,
                         season_id: int) -> CollegeSeasonRecordOut | None:
    """A D-II/D-III program's season (W9e), in the same shape as D-I's."""
    from footsim.world.college import lower

    ls = lower.team_season(conn, world, meta, club_id, season_id)
    defs = lower.rules(world)
    if ls is None or defs is None:
        return None
    d = defs.divisions[ls.division]
    conf = d.conferences[ls.conference]
    label = conn.execute(select(season.c.label).where(season.c.id == season_id)).scalar()
    row = ls.row
    teams = len(lower.conference_tables(conn, world, meta, ls.division, season_id).get(
        ls.conference, []))
    return CollegeSeasonRecordOut(
        season=str(label or ""), conference=conf.short_name, conference_name=conf.name,
        conference_position=row.position if row else None, conference_teams=teams,
        conference_won=row.won if row else 0, conference_drawn=row.drawn if row else 0,
        conference_lost=row.lost if row else 0, conference_points=row.points if row else 0,
        won=ls.record.won, drawn=ls.record.drawn, lost=ls.record.lost,
        goals_for=ls.record.goals_for, goals_against=ls.record.goals_against,
        rpi_rank=ls.rank, ncaa=ls.national, titles=ls.titles, tier=0, prestige=0.0,
        division=ls.division)

RECENT_TRANSFERS = 5


def _recent_transfers(conn: Connection, world: World, club_id: int, names: dict[int, str],
                      currency: str) -> list[str]:
    """A club's latest moves in and out, newest first, in words: "Signed Ali Diallo from Lyon
    for $12M (Aug 2026)". Loans' returns are left out."""
    rows = conn.execute(text("""
        SELECT t.*, COALESCE(p.known_as, p.first_name || ' ' || p.last_name) AS player
        FROM transfer t JOIN person p ON p.id = t.player_id
        WHERE (t.from_club_id = :club OR t.to_club_id = :club) AND t.kind != 'loan_return'
        ORDER BY t.date DESC, t.id DESC LIMIT :n
    """), {"club": club_id, "n": RECENT_TRANSFERS}).all()
    lines = []
    for t in rows:
        when = date.fromisoformat(t.date).strftime("%b %Y")
        fee = money_text(t.fee_cents / 100, world, currency)
        other = t.from_club_id if t.to_club_id == club_id else t.to_club_id
        where = names.get(other, "") if other is not None else ""
        if t.kind == "release":
            line = f"Released {t.player}"
        elif t.kind == "loan":
            line = (f"{t.player} on loan from {where}" if t.to_club_id == club_id
                    else f"{t.player} loaned to {where}")
        elif t.to_club_id == club_id:
            line = (f"Signed {t.player} from {where} for {fee}" if t.fee_cents and where
                    else f"Signed {t.player} on a free")
        else:
            line = (f"Sold {t.player} to {where} for {fee}" if t.fee_cents
                    else f"{t.player} left for {where} on a free")
        lines.append(f"{line} ({when})")
    return lines


def player_detail(conn: Connection, world: World, player_id: int) -> PlayerDetailOut:
    meta = read_meta(conn)
    rows = _player_rows(conn, "p.id = :pid", {"pid": player_id})
    if not rows:
        raise KeyError(player_id)
    r = rows[0]
    attrs = _attributes(conn, [player_id])[player_id]
    fams = _positions(conn, [player_id])[player_id]
    stats = _season_stats(conn, [player_id], meta.season_id).get(player_id)
    started = _season_start_overalls(conn, [player_id], meta.season_id)
    entry = _squad_entry(world, r, attrs, fams, stats, meta.current_date,
                         started.get(player_id), currency=meta.currency)
    entry.college = _college_players(conn, meta, [player_id]).get(player_id)
    values = {a: int(v) for a, v in zip(ATTRIBUTES, attrs, strict=True)}
    grouped: dict[str, list[AttributeOut]] = defaultdict(list)
    for a in ATTRIBUTES:
        grouped[ATTRIBUTE_GROUP[a].value].append(AttributeOut(key=a, value=values[a]))
    role_ratings = world.model.role_overalls(attrs)
    roles = sorted(
        (RoleRatingOut(key=k, name=world.defs.roles[k].name,
                       position_group=world.model.role_groups[i].value,
                       rating=round(float(role_ratings[i])))
         for i, k in enumerate(world.model.role_keys)),
        key=lambda rr: -rr.rating,
    )[:8]
    own = r.club_id == meta.user_club_id
    low, high = potential_range(
        r.pa_hidden, entry.overall, entry.age,
        OWN_CLUB_KNOWLEDGE if own else OTHER_CLUB_KNOWLEDGE, meta.seed, player_id)
    names = _club_names(conn)
    traits = [t.trait for t in conn.execute(
        select(player_trait.c.trait).where(player_trait.c.player_id == player_id))]
    private = {} if own else {"condition": None, "wage_weekly_eur": None}
    weights = world.defs.overall.face_weights[world.defs.positions[entry.position].group]
    return PlayerDetailOut(
        **{**entry.model_dump(), **private},
        club=ClubRef(id=r.club_id, name=names[r.club_id]) if r.club_id else None,
        weight_kg=r.weight_kg, weak_foot=r.weak_foot, skill_moves=r.skill_moves,
        attributes=dict(grouped), face=face_stats(values, goalkeeper=entry.position == "GK"),
        face_key=sorted(weights, key=lambda k: -weights[k])[:3],
        roles=roles, familiarity=fams,
        position_ratings=_position_ratings(world, attrs, fams, entry.position),
        potential=PotentialOut(low=low, high=high, label=potential_label(high)),
        traits=traits, own_player=own, retired=r.retired_on is not None,
        international=_international_career(conn, world, player_id),
    )


def _international_career(conn: Connection, world: World, player_id: int
                          ) -> InternationalCareerOut | None:
    """His national team (the one he has played for or is called up by, else his
    nationality's), with his caps and goals for it (world/international)."""
    played = conn.execute(text(
        "SELECT pm.club_id, COUNT(*) AS caps, SUM(pm.goals) AS goals FROM player_match pm "
        "JOIN fixture f ON f.id = pm.fixture_id JOIN competition c ON c.id = f.competition_id "
        "WHERE pm.player_id = :p AND c.type = :t GROUP BY pm.club_id ORDER BY caps DESC"),
        {"p": player_id, "t": INTERNATIONAL}).first()
    squad = conn.execute(text("SELECT club_id FROM national_squad WHERE player_id = :p"),
                         {"p": player_id}).scalar()
    pooled = conn.execute(text("SELECT code FROM national_pool WHERE player_id = :p"),
                          {"p": player_id}).scalar()
    team_id = played.club_id if played is not None else squad
    if team_id is None:
        code = pooled
        if code is None:
            nation_id = conn.execute(text("SELECT nation_id FROM person WHERE id = :p"),
                                     {"p": player_id}).scalar()
            code = next((c for c, ids in nation_ids(conn, world).items() if nation_id in ids),
                        None)
        if code is None:
            return None
        team_id = conn.execute(text("SELECT club_id FROM national_team WHERE code = :c"),
                               {"c": code}).scalar()
        if team_id is None:
            return None
    name = str(conn.execute(text("SELECT name FROM club WHERE id = :c"),
                            {"c": team_id}).scalar_one())
    return InternationalCareerOut(
        team=ClubRef(id=int(team_id), name=name),
        caps=int(played.caps) if played is not None and played.club_id == team_id else 0,
        goals=int(played.goals or 0) if played is not None and played.club_id == team_id else 0,
        in_squad=squad == team_id, home_based=pooled is not None)


_BANDS = ((18, "natural"), (15, "accomplished"), (11, "competent"), (6, "awkward"),
          (1, "unconvincing"))


def _position_ratings(world: World, attrs: np.ndarray, fams: dict[str, int],
                      primary: str) -> list[PositionRatingOut]:
    """His rating at each position he knows: his best role in its group, times the familiarity
    factor (full from 18, natural)."""
    groups = world.model.group_overalls(attrs)
    result = []
    for pos, fam in fams.items():
        if fam < 1 or pos not in world.defs.positions:
            continue
        full = float(groups[world.defs.positions[pos].group])
        band = next(name for least, name in _BANDS if fam >= least)
        result.append(PositionRatingOut(
            position=pos, name=world.defs.positions[pos].name, familiarity=fam, band=band,
            full_rating=round(full), rating=round(full * familiarity_factor(fam)),
            primary=pos == primary))
    return sorted(result, key=lambda r: (-r.primary, -r.rating, -r.familiarity))


_SEASON_LINES_SQL = """
    SELECT f.season_id, f.competition_id, f.stage, pm.club_id, COUNT(*) AS apps,
           SUM(pm.started) AS starts, SUM(pm.minutes) AS minutes, SUM(pm.goals) AS goals,
           SUM(pm.assists) AS assists, SUM(pm.rating) AS rating_sum, SUM(pm.yellow) AS yellow,
           SUM(pm.red) AS red
    FROM player_match pm JOIN fixture f ON f.id = pm.fixture_id
    WHERE pm.player_id = :pid
    GROUP BY f.season_id, f.competition_id, f.stage, pm.club_id
"""


def _season_line(club_ref: ClubRef | None, key: str, name: str, apps: int, starts: int,
                 minutes: int, goals: int, assists: int, rating_sum: float, yellow: int,
                 red: int, school: bool = False) -> PlayerSeasonLineOut:
    return PlayerSeasonLineOut(
        club=club_ref, competition_key=key, competition=name, appearances=apps, starts=starts,
        minutes=minutes, goals=goals, assists=assists,
        average_rating=round(rating_sum / apps, 2) if apps else None, yellow=yellow, red=red,
        school=school)


@dataclass
class _Line:
    season_id: int
    competition_id: int
    stage: str
    club_id: int
    apps: int
    starts: int
    minutes: int
    goals: int
    assists: int
    rating_sum: float
    yellow: int
    red: int


def _college_merged(conn: Connection, comps: dict[int, Row[Any]], query: Any, player_id: int
                    ) -> list[_Line]:
    """The season lines with a college season's stages (regular season, conference
    tournament, NCAA tournament) as one line: they're one competition."""
    merged: dict[tuple[int, int, str, int], _Line] = {}
    for r in conn.execute(query, {"pid": player_id}):
        college = comps[r.competition_id].type == "college"
        stage = comps[r.competition_id].key if college else str(r.stage)
        key = (int(r.season_id), int(r.competition_id), stage, int(r.club_id))
        line = merged.get(key)
        if line is None:
            merged[key] = _Line(int(r.season_id), int(r.competition_id), stage, int(r.club_id),
                                int(r.apps), int(r.starts or 0), int(r.minutes or 0),
                                int(r.goals or 0), int(r.assists or 0), float(r.rating_sum or 0),
                                int(r.yellow or 0), int(r.red or 0))
        else:
            line.apps += int(r.apps)
            line.starts += int(r.starts or 0)
            line.minutes += int(r.minutes or 0)
            line.goals += int(r.goals or 0)
            line.assists += int(r.assists or 0)
            line.rating_sum += float(r.rating_sum or 0)
            line.yellow += int(r.yellow or 0)
            line.red += int(r.red or 0)
    return list(merged.values())


def player_seasons(conn: Connection, world: World, player_id: int) -> list[PlayerSeasonOut]:
    """A player's record season by season, the current one first: a line for each competition
    he played in (a league's play-offs count as a competition of their own) and a total. A
    retired player keeps his history."""
    if conn.execute(select(person.c.id).where(person.c.id == player_id)).first() is None:
        raise KeyError(player_id)
    names = _club_names(conn)
    comps = _competitions(conn)
    labels = {r.id: r.label for r in conn.execute(select(season))}
    # (season) -> [(sort key, competition key, competition name, row)]
    found: dict[int, list[tuple[tuple[int, int, str], str, str, _Line]]] = defaultdict(list)
    for r in _college_merged(conn, comps, text(_SEASON_LINES_SQL), player_id):
        comp = comps[r.competition_id]
        league = world.defs.leagues.get(comp.key)
        if r.stage == "league" or r.stage == comp.key or league is None:
            key, name = comp.key, comp.name
        else:  # a play-off, named as the league's definition has it
            playoff = next((p for p in league.playoffs if p.key == r.stage), None)
            key, name = r.stage, playoff.name if playoff else f"{comp.name} play-offs"
        kind = 2 if comp.type == "cup" else 0 if r.stage == "league" else 1
        found[r.season_id].append(((kind, comp.tier or 0, name), key, name, r))
    result = []
    for season_id in sorted(found, reverse=True):
        entries = sorted(found[season_id], key=lambda e: e[0])
        rows = [r for _, _, _, r in entries]
        result.append(PlayerSeasonOut(
            season_id=season_id, season=labels[season_id],
            lines=[_season_line(ClubRef(id=r.club_id, name=names[r.club_id]), key, name, r.apps,
                                r.starts, r.minutes, r.goals, r.assists, r.rating_sum, r.yellow,
                                r.red, school=comps[r.competition_id].type == "college")
                   for _, key, name, r in entries],
            total=_season_line(None, "", "All competitions", sum(r.apps for r in rows),
                               sum(r.starts for r in rows), sum(r.minutes for r in rows),
                               sum(r.goals for r in rows), sum(r.assists for r in rows),
                               sum(r.rating_sum for r in rows), sum(r.yellow for r in rows),
                               sum(r.red for r in rows))))
    return result


class SquadTooSmall(Exception):
    """Releasing the player would leave the user's squad unable to field a side."""


def release_player(conn: Connection, world: World, player_id: int, day: date) -> None:
    """End the user's contract with one of their players: he becomes a free agent. Refused
    (SquadTooSmall) when it would leave fewer senior players or keepers than the lifecycle
    rules' floor: the same rule as any move (world/transfers.py)."""
    meta = read_meta(conn)
    owner = owner_contract(conn, player_id)
    if owner is None or owner.club_id != meta.user_club_id:
        raise KeyError(player_id)
    if in_college(conn, player_id):  # a college coach's player leaves the program (W9c)
        try:
            leave_program(conn, world, player_id, day)
        except ValueError as exc:
            raise SquadTooSmall(str(exc)) from exc
        return
    try:
        complete_move(conn, world, meta, Move(player_id, None, by_user=True), day)
    except MoveRefused as exc:
        raise SquadTooSmall(str(exc)) from exc


# --- matches --------------------------------------------------------------------------


def match_detail(conn: Connection, fixture_id: int) -> MatchOut:
    row = conn.execute(select(fixture).where(fixture.c.id == fixture_id)).one()
    names = _club_names(conn)
    comps = _competitions(conn)
    people = {r.id: display_name(r.first_name, r.last_name, r.known_as)
              for r in conn.execute(text("""
                  SELECT p.id, p.first_name, p.last_name, p.known_as FROM person p
                  WHERE p.id IN (SELECT player_id FROM player_match WHERE fixture_id = :f)
                     OR p.id IN (SELECT player_id FROM match_event WHERE fixture_id = :f)
                     OR p.id IN (SELECT other_player_id FROM match_event WHERE fixture_id = :f)
              """), {"f": fixture_id})}
    events = [MatchEventOut(minute=e.minute, label=(event_label(e.period, e.second)
                                                    if e.period and e.second is not None
                                                    else f"{e.minute}'"),
                            period=e.period, second=e.second, type=e.type, club_id=e.club_id,
                            player=people.get(e.player_id), other_player=people.get(
                                e.other_player_id), detail=e.detail)
              for e in conn.execute(text(
                  "SELECT * FROM match_event WHERE fixture_id = :f "
                  "ORDER BY COALESCE(period, 0), minute, COALESCE(second, 0), id"),
                  {"f": fixture_id})]
    lines: dict[int, list[PlayerLineOut]] = defaultdict(list)
    for ln in conn.execute(text(
            "SELECT * FROM player_match WHERE fixture_id = :f ORDER BY started DESC, rating DESC"),
            {"f": fixture_id}):
        lines[ln.club_id].append(PlayerLineOut(
            player_id=ln.player_id, name=people.get(ln.player_id, "?"),
            started=bool(ln.started), minutes=ln.minutes, goals=ln.goals, assists=ln.assists,
            shots=ln.shots, shots_on_target=ln.shots_on_target, passes=ln.passes,
            passes_completed=ln.passes_completed, tackles=ln.tackles,
            interceptions=ln.interceptions, saves=ln.saves, yellow=ln.yellow, red=ln.red,
            rating=ln.rating))
    stats = json.loads(row.stats) if row.stats else None
    return MatchOut(fixture=fixtures_out(conn, [row], names, comps)[0], events=events,
                    home_lines=lines[row.home_club_id], away_lines=lines[row.away_club_id],
                    stats=stats, fast_result=row.sim == FAST_SIM)


# --- tactics --------------------------------------------------------------------------


def _own_view(world: World, p: SquadPlayer) -> tuple[int, list[str]]:
    """A player's overall as the squad shows it (his best role in his main position's group),
    and where he is at home."""
    group = world.defs.positions[p.primary_position].group
    overall = round(float(world.model.group_overalls(p.attrs)[group]))
    home = [pos for pos, fam in sorted(p.positions.items(), key=lambda kv: -kv[1]) if fam >= 15]
    return overall, home


def _fit(familiarity: int) -> str:
    return "natural" if familiarity >= 15 else "adjusted" if familiarity >= 11 else "out"


def _slot_entry(world: World, sp: SheetPlayer) -> SheetEntryOut:
    """A starter with the reasons his rating in the slot differs from his overall."""
    p = sp.player
    overall, home = _own_view(world, p)
    role = world.defs.roles[sp.role]
    role_overall = float(world.model.role_overalls(p.attrs)[world.model.role_index(sp.role)])
    familiarity = p.positions.get(sp.position, 0)
    after_position = role_overall * familiarity_factor(familiarity)
    final = after_position * condition_factor(p.condition)
    step_role = round(role_overall) - overall
    step_position = round(after_position) - round(role_overall)
    step_condition = min(round(final), 99) - round(after_position)
    adjustments = []
    if step_role:
        adjustments.append(RatingAdjustmentOut(
            kind="role", label=f"playing as {role.name}", delta=step_role))
    if step_position:
        adjustments.append(RatingAdjustmentOut(
            kind="position", label=f"out of position at {sp.position}"
            if _fit(familiarity) == "out" else f"not fully at home at {sp.position}",
            delta=step_position))
    if step_condition:
        adjustments.append(RatingAdjustmentOut(
            kind="condition", label=f"not fully fit ({round(p.condition)}%)",
            delta=step_condition))
    return SheetEntryOut(
        slot=sp.slot, position=sp.position, role=sp.role, player_id=sp.player_id,
        name=p.name, number=sp.number, rating=round(sp.rating), condition=round(p.condition),
        overall=overall, best_position=p.primary_position, positions=home,
        familiarity=familiarity, position_fit=_fit(familiarity), role_name=role.name,
        adjustments=adjustments, available=p.available)


def _bench_entry(world: World, p: SquadPlayer, number: int = 0) -> SheetEntryOut:
    """A substitute or a reserve: no slot, so his rating is his overall."""
    overall, home = _own_view(world, p)
    return SheetEntryOut(
        slot=None, position=p.primary_position, role="", player_id=p.player_id, name=p.name,
        number=number, rating=overall, condition=round(p.condition), overall=overall,
        best_position=p.primary_position, positions=home, available=p.available)


def _sheet_entries(world: World, sheet: TeamSheet) -> list[SheetEntryOut]:
    return [_slot_entry(world, sp) for sp in sheet.starters]


def tactics(conn: Connection, world: World, meta: CareerMeta | None = None,
            club_id: int | None = None) -> TacticsOut:
    """The user's club's tactic, or ``club_id``'s (his national team, I5)."""
    meta = meta or read_meta(conn)
    team = club_id or meta.user_club_id
    assert team is not None
    row = conn.execute(select(tactic).where(tactic.c.club_id == team)).first()
    sheet = team_sheet(conn, world, team, meta.current_date)
    squad_players = load_squad(conn, team, meta.current_date)
    defs = world.defs
    lineup = {k: int(v) for k, v in json.loads(row.lineup).items()} if row and row.lineup else None
    used = {sp.player_id for sp in (*sheet.starters, *sheet.bench)}
    order = list(defs.positions)
    reserves = sorted((p for p in squad_players if p.player_id not in used),
                      key=lambda p: (order.index(p.primary_position), -_own_view(world, p)[0]))
    return TacticsOut(
        formation=sheet.formation.key,
        roles=json.loads(row.roles) if row else {},
        lineup=lineup,
        bench_chosen=bool(lineup and any(sub_order(k) is not None for k in lineup)),
        bench_size=BENCH_SIZE,
        instructions={**default_instructions(defs),
                      **(json.loads(row.instructions) if row else {})},
        starters=_sheet_entries(world, sheet),
        bench=[_bench_entry(world, sp.player, sp.number) for sp in sheet.bench],
        reserves=[_bench_entry(world, p) for p in reserves],
        formations=[FormationOut(key=f.key, name=f.name, slots=[
            SlotOut(id=s.id, position=s.position, x=s.base.x, y=s.base.y,
                    default_role=s.default_role) for s in f.slots])
            for f in defs.formations.values()],
        roles_by_group={g.value: [RoleOut(key=r.key, name=r.name, group=r.group.value,
                                          description=r.description)
                                  for r in defs.roles_for(g)]
                        for g in {p.group for p in defs.positions.values()}},
        instruction_options=[InstructionOut(key=d.key, label=d.label, options=d.options,
                                            default=d.default)
                             for d in defs.instructions.values()],
    )
