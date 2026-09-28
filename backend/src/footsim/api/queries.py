"""Read models for the API: squad lists, tables, fixtures, match reports, tactics."""

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import Connection, Row, bindparam, or_, select, text

from footsim.api.schemas import (
    AttributeOut,
    CareerOut,
    ClubOption,
    ClubRef,
    CompetitionOut,
    FixtureOut,
    FormationOut,
    InstructionOut,
    LeagueOption,
    MatchEventOut,
    MatchOut,
    PlayerDetailOut,
    PlayerLineOut,
    PotentialOut,
    RoleOut,
    RoleRatingOut,
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
from footsim.match.teams import TeamSheet
from footsim.persistence.database import open_database
from footsim.persistence.schema import (
    club,
    club_league_membership,
    competition,
    fixture,
    player_attr,
    player_position,
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
from footsim.world.context import World, default_instructions
from footsim.world.meta import CareerMeta, read_meta
from footsim.world.season import active_leagues, standings
from footsim.world.squads import display_name, short_name, team_sheet

# --- helpers --------------------------------------------------------------------------


def _club_names(conn: Connection) -> dict[int, str]:
    return {r.id: r.name for r in conn.execute(select(club.c.id, club.c.name))}


def _competitions(conn: Connection) -> dict[int, Row[Any]]:
    return {r.id: r for r in conn.execute(select(competition))}


def fixture_out(row: Row[Any], names: dict[int, str], comps: dict[int, Row[Any]]) -> FixtureOut:
    comp = comps[row.competition_id]
    return FixtureOut(
        id=row.id, date=row.date, competition=comp.key, competition_name=comp.name,
        stage=row.stage, round=row.round, tie=row.tie, leg=row.leg,
        home=ClubRef(id=row.home_club_id, name=names[row.home_club_id]),
        away=ClubRef(id=row.away_club_id, name=names[row.away_club_id]),
        neutral=bool(row.neutral), status=row.status, home_goals=row.home_goals,
        away_goals=row.away_goals, extra_time=bool(row.extra_time), home_pens=row.home_pens,
        away_pens=row.away_pens,
    )


def _club_competition(conn: Connection, club_id: int, season_id: int) -> Row[Any] | None:
    return conn.execute(select(competition).join(
        club_league_membership, club_league_membership.c.competition_id == competition.c.id,
    ).where(club_league_membership.c.club_id == club_id,
            club_league_membership.c.season_id == season_id)).first()


def _season_label(conn: Connection, season_id: int) -> str:
    return str(conn.execute(select(season.c.label).where(season.c.id == season_id)).scalar_one())


# --- new career -----------------------------------------------------------------------


def world_leagues(base_world: Path, world: World) -> list[LeagueOption]:
    engine = open_database(base_world)
    try:
        with engine.connect() as conn:
            comps = conn.execute(select(competition).order_by(competition.c.tier)).all()
            result = []
            for comp in comps:
                rows = conn.execute(text("""
                    SELECT c.id, c.name, c.reputation FROM club c
                    JOIN club_league_membership m ON m.club_id = c.id
                    WHERE m.competition_id = :comp AND m.season_id = 1
                """), {"comp": comp.id}).all()
                clubs = [ClubOption(id=r.id, name=r.name, reputation=r.reputation,
                                    average_overall=_squad_strength(conn, world, r.id))
                         for r in rows]
                clubs.sort(key=lambda c: -c.average_overall)
                result.append(LeagueOption(key=comp.key, name=comp.name, tier=comp.tier,
                                           clubs=clubs))
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
        manager=meta.manager_name, club=ClubRef(id=user, name=names[user]),
        competition=CompetitionOut(key=comp.key, name=comp.name, tier=comp.tier) if comp else None,
        position=position,
        next_fixture=fixture_out(upcoming, names, comps) if upcoming else None,
        recent=[fixture_out(r, names, comps) for r in recent],
    )


def competitions(conn: Connection, world: World) -> list[CompetitionOut]:
    return [CompetitionOut(key=a.league.key, name=a.league.name, tier=a.league.tier)
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
    rows = [TableRowOut(
        position=r.position, club=ClubRef(id=r.club_id, name=names[r.club_id]),
        played=r.played, won=r.won, drawn=r.drawn, lost=r.lost, goals_for=r.goals_for,
        goals_against=r.goals_against, goal_difference=r.goal_difference, points=r.points,
        zone=zones.get(r.position), form=form.get(r.club_id, []),
    ) for r in ordered]
    return TableOut(competition=key, name=comp.name, season=_season_label(conn, season_id),
                    rows=rows)


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
           s.condition, s.form, s.injured_until, s.injury, s.suspended_matches
    FROM person p
    JOIN player pl ON pl.person_id = p.id
    LEFT JOIN nation n ON n.id = p.nation_id
    LEFT JOIN contract k ON k.person_id = p.id AND k.is_active = 1
    LEFT JOIN player_state s ON s.player_id = p.id
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


def _squad_entry(world: World, r: Row[Any], attrs: np.ndarray, fams: dict[str, int],
                 stats: Row[Any] | None, day: date) -> SquadPlayerOut:
    primary = max(fams, key=lambda pos: fams[pos]) if fams else "CM"
    overall = float(world.model.group_overalls(attrs)[world.defs.positions[primary].group])
    age = age_on(date.fromisoformat(r.birth_date), day)
    injured = r.injured_until if r.injured_until and r.injured_until > day.isoformat() else None
    value = (r.value_eur_cents // 100) if r.value_eur_cents else estimate_value_eur(overall, age)
    return SquadPlayerOut(
        id=r.id, name=display_name(r.first_name, r.last_name, r.known_as),
        short_name=short_name(r.first_name, r.last_name, r.known_as), position=primary,
        positions=[p for p, f in sorted(fams.items(), key=lambda kv: -kv[1]) if f >= 15],
        age=age, nationality=r.nation, overall=round(overall),
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
    order = list(world.defs.positions)
    entries = [_squad_entry(world, r, attrs[r.id], positions[r.id], stats.get(r.id),
                            meta.current_date) for r in rows]
    return sorted(entries, key=lambda e: (order.index(e.position), -e.overall))


def player_detail(conn: Connection, world: World, player_id: int) -> PlayerDetailOut:
    meta = read_meta(conn)
    rows = _player_rows(conn, "p.id = :pid", {"pid": player_id})
    if not rows:
        raise KeyError(player_id)
    r = rows[0]
    attrs = _attributes(conn, [player_id])[player_id]
    fams = _positions(conn, [player_id])[player_id]
    stats = _season_stats(conn, [player_id], meta.season_id).get(player_id)
    entry = _squad_entry(world, r, attrs, fams, stats, meta.current_date)
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
    return PlayerDetailOut(
        **entry.model_dump(),
        club=ClubRef(id=r.club_id, name=names[r.club_id]) if r.club_id else None,
        weight_kg=r.weight_kg, weak_foot=r.weak_foot, skill_moves=r.skill_moves,
        attributes=dict(grouped), face=face_stats(values, goalkeeper=entry.position == "GK"),
        roles=roles, familiarity=fams,
        potential=PotentialOut(low=low, high=high, label=potential_label(high)),
        traits=traits, own_player=own,
    )


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
    events = [MatchEventOut(minute=e.minute, type=e.type, club_id=e.club_id,
                            player=people.get(e.player_id), other_player=people.get(
                                e.other_player_id), detail=e.detail)
              for e in conn.execute(text(
                  "SELECT * FROM match_event WHERE fixture_id = :f ORDER BY minute, id"),
                  {"f": fixture_id})]
    lines: dict[int, list[PlayerLineOut]] = defaultdict(list)
    for ln in conn.execute(text(
            "SELECT * FROM player_match WHERE fixture_id = :f ORDER BY started DESC, rating DESC"),
            {"f": fixture_id}):
        lines[ln.club_id].append(PlayerLineOut(
            player_id=ln.player_id, name=people.get(ln.player_id, "?"),
            started=bool(ln.started), minutes=ln.minutes, goals=ln.goals, assists=ln.assists,
            shots=ln.shots, passes=ln.passes, passes_completed=ln.passes_completed,
            tackles=ln.tackles, saves=ln.saves, yellow=ln.yellow, red=ln.red, rating=ln.rating))
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
