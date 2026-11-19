"""International football's page (W8, world/international): the national teams ranked by Elo,
with their confederations, and the latest international results."""

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from footsim.api import queries
from footsim.api.routes import Session
from footsim.api.schemas import ClubRef, FixtureOut
from footsim.world.context import get_world
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
