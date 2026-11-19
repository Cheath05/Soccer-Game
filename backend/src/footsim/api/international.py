"""International football's page (W8, world/international): the national teams ranked by Elo,
with their confederations, and the latest international results."""

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from footsim.api import queries
from footsim.api.routes import Session
from footsim.api.schemas import ClubRef, FixtureOut
from footsim.world.context import get_world
from footsim.world.international import qualifiers as q
from footsim.world.international.common import TYPE

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
