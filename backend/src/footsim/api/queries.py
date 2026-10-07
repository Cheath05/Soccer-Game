"""Read models for the API: squad lists, tables, fixtures, match reports, tactics."""

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import Connection, Row, bindparam, func, or_, select, text, update

from footsim.api.schemas import (
    AttributeOut,
    CareerOut,
    ClubHistoryOut,
    ClubOption,
    ClubOverviewOut,
    ClubPlayerOut,
    ClubRef,
    ClubSeasonOut,
    CompetitionOut,
    CupOut,
    CupRoundOut,
    CupRunOut,
    CupSummaryOut,
    CupTieOut,
    FixtureOut,
    FormationOut,
    InstructionOut,
    LeagueOption,
    MatchEventOut,
    MatchOut,
    PlayerDetailOut,
    PlayerLineOut,
    PlayerSeasonLineOut,
    PlayerSeasonOut,
    PotentialOut,
    RoleOut,
    RoleRatingOut,
    SeasonOut,
    SheetEntryOut,
    SlotOut,
    SquadPlayerOut,
    TableOut,
    TableRowOut,
    TacticsOut,
)
from footsim.defs.competitions import MovementKind
from footsim.domain.attributes import ATTRIBUTE_GROUP, ATTRIBUTES
from footsim.importers.generate import age_on
from footsim.match.engine.clock import event_label
from footsim.match.teams import TeamSheet
from footsim.persistence.database import open_database
from footsim.persistence.schema import (
    club,
    club_finance,
    club_league_membership,
    competition,
    contract,
    cup_tie,
    fixture,
    league_final,
    nation,
    person,
    player_attr,
    player_position,
    player_season_overall,
    player_trait,
    season,
    tactic,
)
from footsim.ratings.face import face_stats
from footsim.scouting.estimates import (
    OTHER_CLUB_KNOWLEDGE,
    OWN_CLUB_KNOWLEDGE,
    potential_label,
    potential_range,
)
from footsim.transfers.valuation import estimate_value_eur
from footsim.world.context import World, default_instructions, get_world
from footsim.world.cups import cups_in_play, season_cups
from footsim.world.meta import CareerMeta, read_meta
from footsim.world.season import active_leagues, season_calendar, standings
from footsim.world.squads import display_name, short_name, team_sheet

# --- helpers --------------------------------------------------------------------------


def _club_names(conn: Connection) -> dict[int, str]:
    return {r.id: r.name for r in conn.execute(select(club.c.id, club.c.name))}


def _competitions(conn: Connection) -> dict[int, Row[Any]]:
    return {r.id: r for r in conn.execute(select(competition))}


def fixture_out(row: Row[Any], names: dict[int, str], comps: dict[int, Row[Any]]) -> FixtureOut:
    comp = comps[row.competition_id]
    cup = get_world().defs.cups.get(comp.key)
    return FixtureOut(
        id=row.id, date=row.date, competition=comp.key, competition_name=comp.name,
        stage=row.stage, round=row.round, tie=row.tie, leg=row.leg,
        home=ClubRef(id=row.home_club_id, name=names[row.home_club_id]),
        away=ClubRef(id=row.away_club_id, name=names[row.away_club_id]),
        neutral=bool(row.neutral), status=row.status, home_goals=row.home_goals,
        away_goals=row.away_goals, extra_time=bool(row.extra_time), home_pens=row.home_pens,
        away_pens=row.away_pens, stage_name=cup.rounds[row.round].name if cup else None,
    )


def _club_competition(conn: Connection, club_id: int, season_id: int) -> Row[Any] | None:
    return conn.execute(select(competition).join(
        club_league_membership, club_league_membership.c.competition_id == competition.c.id,
    ).where(club_league_membership.c.club_id == club_id,
            club_league_membership.c.season_id == season_id)).first()


def _season_label(conn: Connection, season_id: int) -> str:
    return str(conn.execute(select(season.c.label).where(season.c.id == season_id)).scalar_one())


# --- new career -----------------------------------------------------------------------


def _competition_out(world: World, comp: Row[Any]) -> CompetitionOut:
    league = world.defs.leagues.get(comp.key)
    return CompetitionOut(key=comp.key, name=comp.name, tier=comp.tier or 0,
                          nation=league.nation if league else "")


def world_leagues(base_world: Path, world: World) -> list[LeagueOption]:
    """Every league a career can start in, with its clubs: those the base world was built with,
    and those added since (found by the ratings source's league names, as a new career will)."""
    engine = open_database(base_world)
    try:
        with engine.connect() as conn:
            built = {r.key: r.id for r in conn.execute(select(competition.c.id,
                                                              competition.c.key))}
            result = []
            for key, league in sorted(world.defs.leagues.items(),
                                      key=lambda kv: (kv[1].nation != "ENG", kv[1].nation,
                                                      kv[1].tier)):
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
                clubs = [ClubOption(id=r.id, name=r.name, reputation=r.reputation,
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
        WHERE k.club_id = :club AND k.is_active = 1
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
    assert meta.user_club_id is not None
    names = _club_names(conn)
    comps = _competitions(conn)
    comp = _club_competition(conn, meta.user_club_id, meta.season_id)
    position = None
    if comp is not None:
        table = standings(conn, world, meta, comp.id, meta.season_id)
        if any(r.played for r in table):
            position = next(r.position for r in table if r.club_id == meta.user_club_id)
    user = meta.user_club_id
    upcoming = conn.execute(select(fixture).where(
        fixture.c.status == "scheduled",
        or_(fixture.c.home_club_id == user, fixture.c.away_club_id == user),
    ).order_by(fixture.c.date)).first()
    recent = conn.execute(select(fixture).where(
        fixture.c.status == "played",
        or_(fixture.c.home_club_id == user, fixture.c.away_club_id == user),
    ).order_by(fixture.c.date.desc()).limit(5)).all()
    return CareerOut(
        slot=slot, date=meta.current_date.isoformat(), season=_season_label(conn, meta.season_id),
        season_end=season_calendar(world, meta, meta.season_id).season_end.isoformat(),
        manager=meta.manager_name, club=ClubRef(id=user, name=names[user]),
        competition=_competition_out(world, comp) if comp else None,
        position=position,
        next_fixture=fixture_out(upcoming, names, comps) if upcoming else None,
        recent=[fixture_out(r, names, comps) for r in recent],
    )


def competitions(conn: Connection, world: World) -> list[CompetitionOut]:
    return [CompetitionOut(key=a.league.key, name=a.league.name, tier=a.league.tier,
                           nation=a.league.nation)
            for a in active_leagues(conn, world)]


def table(conn: Connection, world: World, key: str, season_id: int | None = None) -> TableOut:
    meta = read_meta(conn)
    season_id = season_id or meta.season_id
    comp = conn.execute(select(competition).where(competition.c.key == key)).one()
    league = world.defs.leagues[key]
    zones: dict[int, str] = {}
    for mv in league.movements:
        zone = "promotion" if mv.kind is MovementKind.PROMOTION else "relegation"
        for pos in range(mv.ranks[0], mv.ranks[1] + 1):
            zones[pos] = zone
    for playoff in league.playoffs:
        for pos in playoff.entrant_ranks():
            zones[pos] = "playoff"
    if league.tier == 1:
        zones.setdefault(1, "champion")
    names = _club_names(conn)
    form = _form(conn, comp.id, season_id)
    ordered = standings(conn, world, meta, comp.id, season_id)
    if not any(r.played for r in ordered):  # pre-season: alphabetical, like the real thing
        ordered.sort(key=lambda r: names[r.club_id])
        for position, r in enumerate(ordered, start=1):
            r.position = position
    outcomes = {r.club_id: r.outcome for r in conn.execute(select(league_final).where(
        league_final.c.season_id == season_id, league_final.c.competition_id == comp.id))}
    rows = [TableRowOut(
        position=r.position, club=ClubRef(id=r.club_id, name=names[r.club_id]),
        played=r.played, won=r.won, drawn=r.drawn, lost=r.lost, goals_for=r.goals_for,
        goals_against=r.goals_against, goal_difference=r.goal_difference, points=r.points,
        zone=zones.get(r.position), form=form.get(r.club_id, []),
        outcome=outcomes.get(r.club_id),
    ) for r in ordered]
    first_match = conn.execute(select(func.min(fixture.c.date)).where(
        fixture.c.competition_id == comp.id, fixture.c.season_id == season_id,
        fixture.c.stage == "league")).scalar()
    return TableOut(competition=key, name=comp.name, season=_season_label(conn, season_id),
                    final=bool(outcomes), started=any(r.played for r in ordered),
                    first_match=first_match, rows=rows)


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
        comp = comps[comp_id]
        if comp.key in world.defs.cups:
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
        for row in conn.execute(select(fixture).where(
                fixture.c.season_id == season_id, fixture.c.competition_id == comp_id,
        ).order_by(fixture.c.leg)):
            games[(row.round, row.tie)].append(fixture_out(row, names, comps))

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

    def competition_of(comp_id: int) -> CompetitionOut:
        return _competition_out(world, comps[comp_id])

    runs = cup_runs(conn, world, club_id)
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
            outcome=None, final=False, managed=managed, cups=runs.get(meta.season_id, [])))
    for f in finals:
        rows.append(ClubSeasonOut(
            season_id=f.season_id, season=labels[f.season_id],
            competition=competition_of(f.competition_id), position=f.position,
            played=f.played, won=f.won, drawn=f.drawn, lost=f.lost, goals_for=f.goals_for,
            goals_against=f.goals_against, points=f.points, outcome=f.outcome, final=True,
            managed=managed, cups=runs.get(f.season_id, [])))
    def promoted(f: Row[Any]) -> bool:  # a lower league's champions go up too
        return f.outcome in ("promoted", "playoff_winner") or (
            f.outcome == "champion" and (comps[f.competition_id].tier or 1) > 1)

    return ClubHistoryOut(
        club=ClubRef(id=club_id, name=names[club_id]), seasons=rows,
        titles=sum(f.outcome == "champion" for f in finals),
        promotions=sum(promoted(f) for f in finals),
        relegations=sum(f.outcome == "relegated" for f in finals),
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
    return [fixture_out(r, names, comps) for r in rows]


# --- players --------------------------------------------------------------------------

_PLAYER_SQL = """
    SELECT p.id, p.first_name, p.last_name, p.known_as, p.birth_date, n.name AS nation,
           pl.height_cm, pl.weight_kg, pl.preferred_foot, pl.weak_foot, pl.skill_moves,
           pl.pa_hidden, pl.value_eur_cents, k.club_id, k.wage_weekly_cents, k.end_date,
           s.condition, s.form, s.injured_until, s.injury, s.suspended_matches, d.trend,
           pl.retired_on
    FROM person p
    JOIN player pl ON pl.person_id = p.id
    LEFT JOIN nation n ON n.id = p.nation_id
    LEFT JOIN contract k ON k.person_id = p.id AND k.is_active = 1
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
                 stats: Row[Any] | None, day: date,
                 season_start: int | None = None) -> SquadPlayerOut:
    primary = max(fams, key=lambda pos: fams[pos]) if fams else "CM"
    overall = float(world.model.group_overalls(attrs)[world.defs.positions[primary].group])
    age = age_on(date.fromisoformat(r.birth_date), day)
    injured = r.injured_until if r.injured_until and r.injured_until > day.isoformat() else None
    value = (r.value_eur_cents // 100) if r.value_eur_cents else estimate_value_eur(overall, age)
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
        injured_until=injured, suspended=r.suspended_matches or 0, value_eur=int(value),
        wage_weekly_eur=(r.wage_weekly_cents or 0) // 100, contract_end=r.end_date or "",
        height_cm=r.height_cm, preferred_foot=r.preferred_foot,
        appearances=stats.apps if stats else 0, goals=stats.goals or 0 if stats else 0,
        assists=stats.assists or 0 if stats else 0,
        average_rating=round(stats.rating, 2) if stats else None,
    )


def squad(conn: Connection, world: World, club_id: int) -> list[SquadPlayerOut]:
    meta = read_meta(conn)
    rows = _player_rows(conn, "k.club_id = :club", {"club": club_id})
    ids = [r.id for r in rows]
    attrs, positions = _attributes(conn, ids), _positions(conn, ids)
    stats = _season_stats(conn, ids, meta.season_id)
    started = _season_start_overalls(conn, ids, meta.season_id)
    order = list(world.defs.positions)
    entries = [_squad_entry(world, r, attrs[r.id], positions[r.id], stats.get(r.id),
                            meta.current_date, started.get(r.id)) for r in rows]
    return sorted(entries, key=lambda e: (order.index(e.position), -e.overall))


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
    return ClubOverviewOut(
        club=ClubRef(id=club_id, name=row.name), own_club=own, nation=row.nation_name,
        competition=_competition_out(world, comp) if comp else None,
        position=position, points=points, played=played, reputation=row.reputation,
        stadium_name=row.stadium_name, stadium_capacity=row.stadium_capacity,
        manager=meta.manager_name if own else None,
        wage_bill_weekly_eur=int(wage_bill), transfer_budget_eur=int(budget),
        balance_eur=int(balance),
        squad_size=len(players),
        average_age=round(float(np.mean([p.age for p in players])), 1) if players else 0.0,
        average_overall=round(float(np.mean([p.overall for p in players])), 1) if players else 0.0,
        top_players=[_outside_view(p) for p in sorted(players, key=lambda p: -p.overall)[:5]],
        recent=[fixture_out(r, names, comps) for r in recent],
        upcoming=[fixture_out(r, names, comps) for r in upcoming],
        recent_transfers=[],
    )


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
                         started.get(player_id))
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
        potential=PotentialOut(low=low, high=high, label=potential_label(high)),
        traits=traits, own_player=own, retired=r.retired_on is not None,
    )


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
                 red: int) -> PlayerSeasonLineOut:
    return PlayerSeasonLineOut(
        club=club_ref, competition_key=key, competition=name, appearances=apps, starts=starts,
        minutes=minutes, goals=goals, assists=assists,
        average_rating=round(rating_sum / apps, 2) if apps else None, yellow=yellow, red=red)


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
    found: dict[int, list[tuple[tuple[int, int, str], str, str, Row[Any]]]] = defaultdict(list)
    for r in conn.execute(text(_SEASON_LINES_SQL), {"pid": player_id}):
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
                                r.red) for _, key, name, r in entries],
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
    rules' floor, as there are no transfers yet to replace them."""
    meta = read_meta(conn)
    rules = world.defs.lifecycle.squads
    seniors = conn.execute(text("""
        SELECT k.person_id,
               (SELECT position FROM player_position pp WHERE pp.player_id = k.person_id
                ORDER BY familiarity DESC LIMIT 1) AS position
        FROM contract k WHERE k.club_id = :club AND k.is_active = 1 AND k.kind != 'youth'
    """), {"club": meta.user_club_id}).all()
    leaving = [r for r in seniors if r.person_id == player_id]
    if leaving:
        if len(seniors) - 1 < rules.user_min_players:
            raise SquadTooSmall(f"You need at least {rules.user_min_players} senior players.")
        keepers = sum(r.position == "GK" for r in seniors)
        if leaving[0].position == "GK" and keepers - 1 < rules.user_min_keepers:
            raise SquadTooSmall(f"You need at least {rules.user_min_keepers} keepers.")
    updated = conn.execute(update(contract).where(
        contract.c.person_id == player_id, contract.c.is_active == 1,
        contract.c.club_id == meta.user_club_id,
    ).values(is_active=0, end_date=day.isoformat())).rowcount
    if not updated:
        raise KeyError(player_id)


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
    return MatchOut(fixture=fixture_out(row, names, comps), events=events,
                    home_lines=lines[row.home_club_id], away_lines=lines[row.away_club_id],
                    stats=stats)


# --- tactics --------------------------------------------------------------------------


def _sheet_entries(sheet: TeamSheet, bench: bool) -> list[SheetEntryOut]:
    players = sheet.bench if bench else sheet.starters
    return [SheetEntryOut(slot=sp.slot, position=sp.position, role=sp.role,
                          player_id=sp.player_id, name=sp.player.name, number=sp.number,
                          rating=round(sp.rating), condition=round(sp.player.condition))
            for sp in players]


def tactics(conn: Connection, world: World, meta: CareerMeta | None = None) -> TacticsOut:
    meta = meta or read_meta(conn)
    assert meta.user_club_id is not None
    row = conn.execute(select(tactic).where(tactic.c.club_id == meta.user_club_id)).first()
    sheet = team_sheet(conn, world, meta.user_club_id, meta.current_date)
    defs = world.defs
    return TacticsOut(
        formation=sheet.formation.key,
        roles=json.loads(row.roles) if row else {},
        lineup={k: int(v) for k, v in json.loads(row.lineup).items()} if row and row.lineup
        else None,
        instructions={**default_instructions(defs),
                      **(json.loads(row.instructions) if row else {})},
        starters=_sheet_entries(sheet, bench=False),
        bench=_sheet_entries(sheet, bench=True),
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
