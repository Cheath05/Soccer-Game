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
from footsim.world.international import editions, manager
from footsim.world.international import finals as wcf
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


FINALS_SHOWN_DAYS = 120  # the finals page shows an edition this long after its final


def _edition(world: Any, conn: Any, year: int | None, keep_days: int) -> editions.Edition:
    """The ``year`` edition, else the one being played or the next."""
    if year is None:
        return editions.current(world, read_meta(conn).current_date, keep_days)
    if not world.defs.international.world_cup.is_edition(year):
        raise HTTPException(404, f"no World Cup in {year}")
    return editions.edition(world, year)


@router.get("/qualifiers")
def qualifiers_view(session: Session, year: int | None = None) -> QualifiersOut:
    """A World Cup's qualifiers (``year``'s, else the one being played or the next): every
    stage's groups and ties, and who is through."""
    world = get_world()
    with session.read() as conn:
        ed = _edition(world, conn, year, 0)
        teams = q._Teams.load(conn)
        names = queries._club_names(conn)
        comps = queries._competitions(conn)
        ref = {code: ClubRef(id=c, name=teams.name[c]) for c, code in teams.code.items()}
        stages = []
        for stage in ed.stages:
            rows = conn.execute(text("SELECT * FROM fixture WHERE stage = :s ORDER BY date, id"),
                                {"s": ed.qualifier_stage(stage.key)}).all()
            groups, ties = [], []
            if stage.format == "groups":
                for letter, table in q.group_tables(conn, ed.qualifier_stage(stage.key),
                                                    teams).items():
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
        # The hosts are through once the qualifiers have started.
        through = q.qualified_teams(conn, ed) if any(s.drawn for s in stages) else {}
    return QualifiersOut(cycle=ed.year, stages=stages, qualified=[
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
def club_world_cup_view(session: Session, year: int | None = None) -> ClubWorldCupOut:
    """A Club World Cup (``year``'s, else the next or current one): its entrants, groups and
    knockout rounds."""
    world = get_world()
    spec = world.defs.international.club_world_cup
    if year is not None and (year < spec.first_year
                             or (year - spec.first_year) % spec.every_years):
        raise HTTPException(404, f"no Club World Cup in {year}")
    with session.read() as conn:
        today = read_meta(conn).current_date
        if year is None:
            year = spec.first_year
            while date(year, 7, 31) < today:
                year += spec.every_years
        state = cwc._get(conn, cwc._meta_key(year)) or {}
        names = queries._club_names(conn)
        comps = queries._competitions(conn)
        entrants = [CwcEntrantOut(team=ClubRef(id=e["club_id"], name=names[e["club_id"]]),
                                  confederation=e["confederation"], how=e["how"])
                    for e in state.get("entrants", [])]
        played: dict[int, int] = {}
        for f in cwc.edition_fixtures(conn, year, cwc.GROUPS):
            if f.status == "played":
                for c in (f.home_club_id, f.away_club_id):
                    played[c] = played.get(c, 0) + 1
        groups = [GroupOut(name=f"Group {letter}", rows=[GroupRowOut(
            team=ClubRef(id=r.club_id, name=names[r.club_id]), played=played.get(r.club_id, 0),
            points=r.points, gd=r.gd, gf=r.gf) for r in table])
            for letter, table in cwc.group_tables(conn, year).items()] if state else []
        rounds = []
        for rnd in cwc.ROUNDS:
            rows = sorted(cwc.edition_fixtures(conn, year, f"CWC:{rnd}"),
                          key=lambda f: int(f.tie))
            if rows:
                rounds.append(CwcRoundOut(name=cwc.ROUND_NAMES[rnd],
                                          fixtures=queries.fixtures_out(conn, rows, names, comps)))
    return ClubWorldCupOut(year=year, draw=cwc.draw_date(world, year).isoformat(),
                           host=spec.host, entrants=entrants, groups=groups, rounds=rounds)


# --- the World Cup finals (W8 I4) --------------------------------------------------------


class WorldCupOut(BaseModel):
    year: int
    draw: str  # ISO date, once qualifying is over
    groups: list[GroupOut]  # empty before the draw
    rounds: list[CwcRoundOut]  # the knockouts so far
    champion: ClubRef | None


@router.get("/world-cup")
def world_cup_view(session: Session, year: int | None = None) -> WorldCupOut:
    """A World Cup's finals (``year``'s, else the one being played, or just played, or the
    next): the groups once drawn, the knockouts so far and the champion."""
    world = get_world()
    with session.read() as conn:
        ed = _edition(world, conn, year, FINALS_SHOWN_DAYS)
        spec = ed.dates
        state = wcf.state(conn, ed) or {}
        names = queries._club_names(conn)
        comps = queries._competitions(conn)
        elo = {int(r.club_id): float(r.elo) for r in conn.execute(text(
            "SELECT club_id, elo FROM national_team"))}
        played: dict[int, int] = {}
        for f in conn.execute(text("SELECT home_club_id, away_club_id FROM fixture "
                                   "WHERE stage = :s AND status = 'played'"), {"s": ed.groups}):
            for c in (f.home_club_id, f.away_club_id):
                played[c] = played.get(c, 0) + 1
        groups = [GroupOut(name=f"Group {letter}", rows=[GroupRowOut(
            team=ClubRef(id=r.club_id, name=names[r.club_id]), played=played.get(r.club_id, 0),
            points=r.points, gd=r.gd, gf=r.gf) for r in table])
            for letter, table in wcf.group_tables(conn, ed, elo).items()]
        rounds = []
        for rnd in ("R32", "R16", "QF", "SF", "3P", "F"):
            rows = wcf.round_fixtures(conn, ed, rnd)
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


# --- history (22 Nov) ----------------------------------------------------------------------


class PastFinalOut(BaseModel):
    year: int
    hosts: list[str]  # the hosts' names
    champion: ClubRef
    runner_up: ClubRef
    score: str  # the final's, the champion's goals first: "2-1", "1-1 (4-3 pens)", "2-1 aet"
    fixture_id: int
    third: ClubRef | None = None  # the World Cup's third-place play-off's winner


class CupHistoryOut(BaseModel):
    world_cup: list[PastFinalOut]  # every World Cup played in the career, the latest first
    club_world_cup: list[PastFinalOut]


def _final(f: Any, year: int, hosts: list[str], names: dict[int, str],
           third: int | None) -> PastFinalOut | None:
    won = wcf._winner(f)
    if won is None:
        return None
    lost = int(f.away_club_id if won == f.home_club_id else f.home_club_id)
    home = won == f.home_club_id
    goals = (f.home_goals, f.away_goals) if home else (f.away_goals, f.home_goals)
    score = f"{goals[0]}-{goals[1]}"
    if f.home_pens is not None:
        pens = (f.home_pens, f.away_pens) if home else (f.away_pens, f.home_pens)
        score += f" ({pens[0]}-{pens[1]} pens)"
    elif f.extra_time:
        score += " aet"
    return PastFinalOut(year=year, hosts=hosts, champion=ClubRef(id=won, name=names[won]),
                        runner_up=ClubRef(id=lost, name=names[lost]), score=score,
                        fixture_id=int(f.id),
                        third=ClubRef(id=third, name=names[third]) if third else None)


@router.get("/history")
def cup_history(session: Session) -> CupHistoryOut:
    """Every World Cup and Club World Cup final played in the career: the champions, the
    runners-up and the scores."""
    world = get_world()
    cup = world.defs.international.world_cup
    with session.read() as conn:
        names = queries._club_names(conn)
        by_code = {str(r.code): str(r.name) for r in conn.execute(text(
            "SELECT n.code, c.name FROM national_team n JOIN club c ON c.id = n.club_id"))}
        rows = conn.execute(text(
            "SELECT * FROM fixture WHERE status = 'played' AND (stage IN (:f, :t, :c) "
            "OR stage GLOB :later_f OR stage GLOB :later_t) ORDER BY date"),
            {"f": "WCF:F", "t": "WCF:3P", "c": "CWC:F", "later_f": "WCF:[0-9]*:F",
             "later_t": "WCF:[0-9]*:3P"}).all()

        def wc_year(stage: str) -> int:
            parts = stage.split(":")
            return int(parts[1]) if len(parts) == 3 else cup.year

        thirds = {wc_year(f.stage): wcf._winner(f) for f in rows if f.stage.endswith(":3P")}
        world_cup, club = [], []
        for f in rows:
            if f.stage == "CWC:F":
                year = int(str(f.date)[:4])
                host = world.defs.international.club_world_cup.host
                found = _final(f, year, [by_code.get(host, host)], names, None)
                if found:
                    club.append(found)
            elif f.stage.endswith(":F"):
                year = wc_year(f.stage)
                hosts = [by_code.get(h, h) for h in editions.edition(world, year).hosts]
                found = _final(f, year, hosts, names, thirds.get(year))
                if found:
                    world_cup.append(found)
    return CupHistoryOut(world_cup=world_cup[::-1], club_world_cup=club[::-1])
