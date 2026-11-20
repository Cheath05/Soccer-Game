"""International football's page (W8, world/international): the national teams ranked by Elo,
with their confederations, and the latest international results."""

import json
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from footsim.api import queries
from footsim.api.routes import Session, _not_simulating
from footsim.api.schemas import ClubRef, FixtureOut
from footsim.world.context import get_world
from footsim.world.international import club_world_cup as cwc
from footsim.world.international import finals as wcf
from footsim.world.international import manager
from footsim.world.international import qualifiers as q
from footsim.world.international.common import TYPE
from footsim.world.meta import read_meta

router = APIRouter(prefix="/api/international")
RESULTS = 40  # the latest international results shown


class RankedTeamOut(BaseModel):
    rank: int  # by Elo, worldwide
    team: ClubRef
    code: str
    confederation: str
    elo: int
    change: int  # since the career began (teams.yaml)


class InternationalOut(BaseModel):
    teams: list[RankedTeamOut]  # best first
    results: list[FixtureOut]  # the latest first


@router.get("")
def international(session: Session) -> InternationalOut:
    teams = get_world().defs.international.teams
    with session.read() as conn:
        rows = conn.execute(text(
            "SELECT t.club_id, t.code, t.confederation, t.elo, c.name FROM national_team t "
            "JOIN club c ON c.id = t.club_id ORDER BY t.elo DESC, t.code")).all()
        ranked = [RankedTeamOut(rank=k, team=ClubRef(id=r.club_id, name=r.name), code=r.code,
                                confederation=r.confederation, elo=round(r.elo),
                                change=round(r.elo - teams[r.code].elo) if r.code in teams else 0)
                  for k, r in enumerate(rows, start=1)]
        played = conn.execute(text(
            "SELECT f.* FROM fixture f JOIN competition c ON c.id = f.competition_id "
            "WHERE c.type = :t AND f.status = 'played' ORDER BY f.date DESC, f.id DESC "
            "LIMIT :n"), {"t": TYPE, "n": RESULTS}).all()
        results = queries.fixtures_out(conn, played, queries._club_names(conn),
                                       queries._competitions(conn))
    return InternationalOut(teams=ranked, results=results)


# --- the World Cup qualifiers (W8 I3) ----------------------------------------------------


class GroupRowOut(BaseModel):
    team: ClubRef
    played: int
    points: int
    gd: int
    gf: int


class GroupOut(BaseModel):
    name: str  # "Group A"
    rows: list[GroupRowOut]


class TieOut(BaseModel):
    tie: str  # "A-SF1", "A-F"
    name: str  # "Path A, semi-final"
    fixtures: list[FixtureOut]


class StageOut(BaseModel):
    key: str
    name: str
    confederation: str
    starts: str  # its first window's month, "YYYY-MM"
    drawn: bool
    qualified_ranks: list[int] | None  # groups: the ranks that qualify
    groups: list[GroupOut]
    ties: list[TieOut]


class QualifiedOut(BaseModel):
    team: ClubRef
    how: str


class QualifiersOut(BaseModel):
    cycle: int
    stages: list[StageOut]
    qualified: list[QualifiedOut]


def _tie_name(tie: str) -> str:
    path, part = tie.split("-")
    return f"Path {path}, " + ("final" if part == "F" else f"semi-final {part[2:]}")


@router.get("/qualifiers")
def qualifiers_view(session: Session) -> QualifiersOut:
    """The World Cup qualifiers: every stage's groups and ties, and who is through."""
    world = get_world()
    spec = world.defs.international.qualifiers
    with session.read() as conn:
        teams = q._Teams.load(conn)
        names = queries._club_names(conn)
        comps = queries._competitions(conn)
        ref = {code: ClubRef(id=c, name=teams.name[c]) for c, code in teams.code.items()}
        stages = []
        for stage in spec.stages:
            rows = conn.execute(text("SELECT * FROM fixture WHERE stage = :s ORDER BY date, id"),
                                {"s": q.STAGE + stage.key}).all()
            groups, ties = [], []
            if stage.format == "groups":
                for letter, table in q.group_tables(conn, stage.key, teams).items():
                    groups.append(GroupOut(name=f"Group {letter}", rows=[GroupRowOut(
                        team=ClubRef(id=r.club_id, name=teams.name[r.club_id]),
                        played=r.played, points=r.points, gd=r.gd, gf=r.gf) for r in table]))
            else:
                by_tie: dict[str, list[object]] = {}
                for f in rows:
                    by_tie.setdefault(f.tie, []).append(f)
                for tie in sorted(by_tie):
                    ties.append(TieOut(tie=tie, name=_tie_name(tie), fixtures=queries.fixtures_out(
                        conn, by_tie[tie], names, comps)))  # type: ignore[arg-type]
            stages.append(StageOut(
                key=stage.key, name=stage.name, confederation=stage.confederation,
                starts=stage.windows[0], drawn=bool(rows),
                qualified_ranks=(list(range(stage.qualified_ranks[0],
                                            stage.qualified_ranks[1] + 1))
                                 if stage.qualified_ranks else None),
                groups=groups, ties=ties))
        through = q.qualified_teams(conn)
    return QualifiersOut(cycle=spec.cycle, stages=stages, qualified=[
        QualifiedOut(team=ref[code], how=how) for code, how in sorted(
            through.items(), key=lambda t: (t[1] != "Hosts", ref[t[0]].name)) if code in ref])


# --- the Club World Cup (W10) ------------------------------------------------------------


class CwcEntrantOut(BaseModel):
    team: ClubRef
    confederation: str
    how: str  # Champions League winners | UEFA club coefficient | Ranking | Guest | Hosts


class CwcRoundOut(BaseModel):
    name: str
    fixtures: list[FixtureOut]


class ClubWorldCupOut(BaseModel):
    year: int
    draw: str  # the draw's day
    host: str  # a FIFA code
    entrants: list[CwcEntrantOut]  # empty before the draw
    groups: list[GroupOut]
    rounds: list[CwcRoundOut]


@router.get("/club-world-cup")
def club_world_cup_view(session: Session) -> ClubWorldCupOut:
    """The next (or current) Club World Cup: its entrants, groups and knockout rounds."""
    world = get_world()
    spec = world.defs.international.club_world_cup
    with session.read() as conn:
        today = read_meta(conn).current_date
        year = spec.first_year
        while date(year, 7, 31) < today:
            year += spec.every_years
        state = cwc._get(conn, cwc._meta_key(year)) or {}
        names = queries._club_names(conn)
        comps = queries._competitions(conn)
        entrants = [CwcEntrantOut(team=ClubRef(id=e["club_id"], name=names[e["club_id"]]),
                                  confederation=e["confederation"], how=e["how"])
                    for e in state.get("entrants", [])]
        groups = [GroupOut(name=f"Group {letter}", rows=[GroupRowOut(
            team=ClubRef(id=r.club_id, name=names[r.club_id]), played=_played(conn, r.club_id),
            points=r.points, gd=r.gd, gf=r.gf) for r in table])
            for letter, table in cwc.group_tables(conn).items()] if state else []
        rounds = []
        for rnd in cwc.ROUNDS:
            rows = conn.execute(text("SELECT * FROM fixture WHERE stage = :s "
                                     "ORDER BY CAST(tie AS INTEGER)"), {"s": f"CWC:{rnd}"}).all()
            if rows:
                rounds.append(CwcRoundOut(name=cwc.ROUND_NAMES[rnd],
                                          fixtures=queries.fixtures_out(conn, rows, names, comps)))
    return ClubWorldCupOut(year=year, draw=cwc.draw_date(world, year).isoformat(),
                           host=spec.host, entrants=entrants, groups=groups, rounds=rounds)


def _played(conn: Any, club_id: int) -> int:
    return int(conn.execute(text(
        "SELECT COUNT(*) FROM fixture WHERE stage = 'CWC:G' AND status = 'played' "
        "AND (home_club_id = :c OR away_club_id = :c)"), {"c": club_id}).scalar_one())


# --- the World Cup finals (W8 I4) --------------------------------------------------------


class WorldCupOut(BaseModel):
    year: int
    draw: str  # ISO date, once qualifying is over
    groups: list[GroupOut]  # empty before the draw
    rounds: list[CwcRoundOut]  # the knockouts so far
    champion: ClubRef | None


@router.get("/world-cup")
def world_cup_view(session: Session) -> WorldCupOut:
    """The World Cup finals: the groups once drawn, the knockouts so far and the champion."""
    spec = get_world().defs.international.world_cup
    with session.read() as conn:
        state = wcf._get(conn) or {}
        names = queries._club_names(conn)
        comps = queries._competitions(conn)
        elo = {int(r.club_id): float(r.elo) for r in conn.execute(text(
            "SELECT club_id, elo FROM national_team"))}
        played: dict[int, int] = {}
        for f in conn.execute(text("SELECT home_club_id, away_club_id FROM fixture "
                                   "WHERE stage = :s AND status = 'played'"), {"s": wcf.GROUPS}):
            for c in (f.home_club_id, f.away_club_id):
                played[c] = played.get(c, 0) + 1
        groups = [GroupOut(name=f"Group {letter}", rows=[GroupRowOut(
            team=ClubRef(id=r.club_id, name=names[r.club_id]), played=played.get(r.club_id, 0),
            points=r.points, gd=r.gd, gf=r.gf) for r in table])
            for letter, table in wcf.group_tables(conn, elo).items()]
        rounds = []
        for rnd in ("R32", "R16", "QF", "SF", "3P", "F"):
            rows = conn.execute(text("SELECT * FROM fixture WHERE stage = :s "
                                     "ORDER BY CAST(tie AS INTEGER)"), {"s": f"WCF:{rnd}"}).all()
            if rows:
                rounds.append(CwcRoundOut(name=wcf.ROUND_NAMES[rnd],
                                          fixtures=queries.fixtures_out(conn, rows, names, comps)))
        champion = state.get("champion")
    return WorldCupOut(year=spec.year, draw=spec.draw, groups=groups, rounds=rounds,
                       champion=ClubRef(id=champion, name=names[champion]) if champion else None)


# --- the user's national team (W8 I5) ----------------------------------------------------


class CallUpOut(BaseModel):
    id: int
    name: str
    position: str
    age: int
    overall: int
    club: ClubRef | None  # None: a made-up home-based player
    injured: bool
    selected: bool


class MyNationOut(BaseModel):
    team: ClubRef | None  # None: no national team job
    code: str | None
    squad_size: int  # the most he can call up
    players: list[CallUpOut]  # the eligible players, the best first
    fixtures: list[FixtureOut]  # the team's next matches


class JobIn(BaseModel):
    code: str  # FIFA code


class SquadIn(BaseModel):
    player_ids: list[int]


def _my_nation(conn: Any) -> MyNationOut:
    world = get_world()
    meta = read_meta(conn)
    size = manager.squad_size(world)
    if meta.user_nation_id is None:
        return MyNationOut(team=None, code=None, squad_size=size, players=[], fixtures=[])
    names = queries._club_names(conn)
    found = manager.candidates(conn, world, meta)
    ids = json.dumps([c.player_id for c in found])
    people = {int(r.id): r for r in conn.execute(text(
        "SELECT id, COALESCE(NULLIF(known_as, ''), first_name || ' ' || last_name) AS name, "
        "birth_date FROM person WHERE id IN (SELECT value FROM json_each(:i))"), {"i": ids})}
    clubs: dict[int, int] = {}
    for r in conn.execute(text(
            "SELECT person_id, club_id, kind FROM contract WHERE is_active = 1 "
            "AND kind != 'staff' AND person_id IN (SELECT value FROM json_each(:i)) "
            "ORDER BY kind = 'loan'"), {"i": ids}):
        clubs[int(r.person_id)] = int(r.club_id)  # a loan (sorted last) wins
    for r in conn.execute(text("SELECT player_id, club_id FROM guest_player")):
        clubs.setdefault(int(r.player_id), int(r.club_id))
    today = meta.current_date
    injured = {int(r[0]) for r in conn.execute(text(
        "SELECT player_id FROM player_state WHERE injured_until > :d"), {"d": today.isoformat()})}

    def age(birth: str) -> int:
        b = date.fromisoformat(birth)
        return today.year - b.year - ((today.month, today.day) < (b.month, b.day))

    players = [CallUpOut(id=c.player_id, name=people[c.player_id].name, position=c.position,
                         age=age(people[c.player_id].birth_date), overall=round(c.overall),
                         club=(ClubRef(id=clubs[c.player_id], name=names[clubs[c.player_id]])
                               if c.player_id in clubs else None),
                         injured=c.player_id in injured, selected=c.selected)
               for c in found if c.player_id in people]
    team = meta.user_nation_id
    upcoming = conn.execute(text(
        "SELECT * FROM fixture WHERE status = 'scheduled' AND (home_club_id = :t OR "
        "away_club_id = :t) ORDER BY date, id LIMIT 6"), {"t": team}).all()
    return MyNationOut(team=ClubRef(id=team, name=names[team]),
                       code=manager.nation_code(conn, team), squad_size=size, players=players,
                       fixtures=queries.fixtures_out(conn, upcoming, names,
                                                     queries._competitions(conn)))


@router.get("/my-team")
def my_team(session: Session) -> MyNationOut:
    """The national team the user manages (if any): the players he can call up, his squad and
    the team's next matches."""
    with session.read() as conn:
        return _my_nation(conn)


@router.post("/job")
def take_job(body: JobIn, session: Session) -> MyNationOut:
    """Take a national team's job (any nation, for now), alongside the club or, without one,
    in place of the one he has."""
    _not_simulating(session)
    with session.write() as conn:
        meta = read_meta(conn)
        if session.live_matches:
            raise HTTPException(409, "finish the match being watched first")
        try:
            manager.take_job(conn, get_world(), meta, body.code, meta.current_date)
        except manager.JobRefused as exc:
            raise HTTPException(404, str(exc)) from exc
    session.autosave()
    with session.read() as conn:
        return _my_nation(conn)


@router.delete("/job")
def leave_job(session: Session) -> MyNationOut:
    _not_simulating(session)
    with session.write() as conn:
        meta = read_meta(conn)
        if session.live_matches:
            raise HTTPException(409, "finish the match being watched first")
        if meta.user_club_id is None:
            raise HTTPException(409, "your country is your only team: take another country's "
                                     "job instead of leaving")
        manager.leave_job(conn, meta)
    session.autosave()
    with session.read() as conn:
        return _my_nation(conn)


@router.put("/my-team/squad")
def put_squad(body: SquadIn, session: Session) -> MyNationOut:
    """The user's call-ups for his national team."""
    _not_simulating(session)
    with session.write() as conn:
        try:
            manager.set_squad(conn, get_world(), read_meta(conn), body.player_ids)
        except manager.JobRefused as exc:
            raise HTTPException(400, str(exc)) from exc
    session.autosave()
    with session.read() as conn:
        return _my_nation(conn)
