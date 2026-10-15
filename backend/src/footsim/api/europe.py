"""The European competitions' pages (W6 E7): what's on this season, and each competition's
qualifying round, league-phase table and matchdays, and knockout rounds. Presentation only:
the rules are in world/europe/."""

from collections import defaultdict
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import Connection, Row, select

from footsim.api.queries import _club_names, _competitions, _season_label, fixture_out
from footsim.api.routes import Session
from footsim.api.schemas import ClubRef, CupRoundOut, CupTieOut, FixtureOut, TableRowOut
from footsim.core.text import ordinal
from footsim.defs.europe import ContinentalDef
from footsim.persistence.schema import (
    club,
    continental_entry,
    cup_tie,
    fixture,
    nation,
)
from footsim.world.context import World, get_world
from footsim.world.europe.common import KNOCKOUT, QUALIFYING, competitions_by_rank, europe_calendar
from footsim.world.europe.league_phase import table
from footsim.world.meta import read_meta

router = APIRouter(prefix="/api")


class EntryOut(BaseModel):
    club: ClubRef
    nation: str
    how: str  # how it got its place: "4th in the Premier League", "FA Cup winners"...
    stage: str  # league_phase | qualifying
    pot: int | None
    position: int | None


class MatchdayOut(BaseModel):
    round: int
    dates: list[str]
    fixtures: list[FixtureOut]


class LeaguePhaseOut(BaseModel):
    drawn: bool
    final: bool  # every matchday played: the table is the final one
    matches: int  # each club's
    to_round_of_16: int  # the places going straight through
    to_playoff: tuple[int, int]  # the places going into the knockout play-off
    table: list[TableRowOut]  # zone: round_of_16 | playoff | out
    matchdays: list[MatchdayOut]


class EuropeOut(BaseModel):
    key: str
    name: str
    short_name: str
    season: str
    qualifying: CupRoundOut
    league_phase: LeaguePhaseOut
    knockout: list[CupRoundOut]
    entries: list[EntryOut]
    winner: ClubRef | None


class EuropeSummaryOut(BaseModel):
    key: str
    name: str
    short_name: str
    stage: str | None  # what's under way or next: "League phase, matchday 3 of 8"
    user_status: str | None  # the user's club: "In the league phase: 5th", "Out in the..."
    winner: ClubRef | None


class EuropeListOut(BaseModel):
    enabled: bool  # whether this game has the European competitions
    competitions: list[EuropeSummaryOut]


def _how(world: World, route: str, nations: dict[str, str]) -> str:
    """A place's route in words: league:ENG:4 is "4th in the Premier League"."""
    kind, _, rest = route.partition(":")
    if kind == "league":
        code, _, rank = rest.partition(":")
        top = next((lg for lg in world.defs.leagues.values()
                    if lg.nation == code and lg.tier == 1), None)
        country = nations.get(code, code)
        if top is None:  # a country without a league in the game
            if rank == "1":
                return f"{country}'s champions"
            return f"{ordinal(int(rank))} in {country}"
        return f"{ordinal(int(rank))} in the {top.name}"
    if kind == "cup":
        cup = world.defs.cups.get(rest)
        return f"{cup.name} winners" if cup else "Cup winners"
    if kind == "holder":
        comp = world.defs.continental.get(rest)
        return f"{comp.name} holders" if comp else "Holders"
    if kind == "fill":
        return f"An extra place for {nations.get(rest, rest)}"
    if kind == "dropped":
        comp = world.defs.continental.get(rest)
        return f"From the {comp.name} play-off round" if comp else "From qualifying"
    return route


def _rounds(world: World, comp: ContinentalDef, comp_id: int | None, season_id: int,
            conn: Connection, names: dict[int, str], comps: dict[int, Row[Any]]
            ) -> tuple[CupRoundOut, list[CupRoundOut], list[FixtureOut]]:
    ties = (conn.execute(select(cup_tie).where(
        cup_tie.c.season_id == season_id, cup_tie.c.competition_id == comp_id)
        .order_by(cup_tie.c.round, cup_tie.c.id)).all() if comp_id is not None else [])
    games: dict[tuple[int, str | None], list[FixtureOut]] = defaultdict(list)
    phase_games: list[FixtureOut] = []
    if comp_id is not None:
        for row in conn.execute(select(fixture).where(
                fixture.c.season_id == season_id, fixture.c.competition_id == comp_id)
                .order_by(fixture.c.round, fixture.c.leg, fixture.c.date, fixture.c.id)):
            out = fixture_out(row, names, comps)
            if QUALIFYING < row.round < KNOCKOUT:
                phase_games.append(out)
            else:
                games[(row.round, row.tie)].append(out)
    dates = europe_calendar(world, season_id).competitions[comp.key]

    def ref(club_id: int | None) -> ClubRef | None:
        return ClubRef(id=club_id, name=names[club_id]) if club_id else None

    def round_out(index: int, number: int, name: str, legs: int,
                  days: list[list[date]]) -> CupRoundOut:
        in_round = [t for t in ties if t.round == number]
        return CupRoundOut(
            index=index, name=name, dates=[min(leg).isoformat() for leg in days], legs=legs,
            drawn=bool(in_round),
            ties=[CupTieOut(tie=t.tie, home=ClubRef(id=t.club_a_id, name=names[t.club_a_id]),
                            away=ref(t.club_b_id), fixtures=games.get((number, t.tie), []),
                            winner=ref(t.winner_club_id)) for t in in_round])

    qualifying = round_out(0, QUALIFYING, comp.qualifying.name, comp.qualifying.legs,
                           dates.qualifying)
    knockout = [round_out(k, KNOCKOUT + k, rnd.name, rnd.legs, dates.knockout[k])
                for k, rnd in enumerate(comp.knockout)]
    return qualifying, knockout, phase_games


def europe(conn: Connection, world: World, key: str, season_id: int | None = None) -> EuropeOut:
    meta = read_meta(conn)
    season_id = season_id or meta.season_id
    comp = world.defs.continental[key]
    names = _club_names(conn)
    comps = _competitions(conn)
    comp_id = next((cid for cid, r in comps.items() if r.key == key), None)
    qualifying, knockout, phase_games = _rounds(world, comp, comp_id, season_id, conn,
                                                names, comps)
    nations = {r.code: r.name for r in conn.execute(select(nation.c.code, nation.c.name))}
    entries = (conn.execute(select(continental_entry, nation.c.code).join(
        club, club.c.id == continental_entry.c.club_id).join(
        nation, nation.c.id == club.c.nation_id).where(
        continental_entry.c.season_id == season_id,
        continental_entry.c.competition_id == comp_id)).all() if comp_id is not None else [])
    phase = comp.league_phase
    rows = table(conn, meta, season_id, comp) if phase_games else []
    first, last = phase.to_playoff

    def zone(position: int) -> str:
        if position <= phase.to_round_of_16:
            return "round_of_16"
        return "playoff" if first <= position <= last else "out"

    by_round: dict[int, list[FixtureOut]] = defaultdict(list)
    for game in phase_games:
        by_round[game.round].append(game)
    dates = europe_calendar(world, season_id).competitions[key].league_phase
    final = bool(phase_games) and all(g.status == "played" for g in phase_games)
    league_phase = LeaguePhaseOut(
        drawn=bool(phase_games), final=final, matches=phase.matches,
        to_round_of_16=phase.to_round_of_16, to_playoff=phase.to_playoff,
        table=[TableRowOut(position=r.position, club=ClubRef(id=r.club_id, name=names[r.club_id]),
                           played=r.played, won=r.won, drawn=r.drawn, lost=r.lost,
                           goals_for=r.goals_for, goals_against=r.goals_against,
                           goal_difference=r.goal_difference, points=r.points,
                           zone=zone(r.position), form=[]) for r in rows],
        matchdays=[MatchdayOut(round=k, dates=[d.isoformat() for d in days],
                               fixtures=by_round.get(k, []))
                   for k, days in enumerate(dates, start=1)])
    final_round = knockout[-1]
    winner = final_round.ties[0].winner if final_round.ties else None
    return EuropeOut(
        key=key, name=comp.name, short_name=comp.short_name,
        season=_season_label(conn, season_id), qualifying=qualifying,
        league_phase=league_phase, knockout=knockout, winner=winner,
        entries=sorted((EntryOut(club=ClubRef(id=e.club_id, name=names[e.club_id]),
                                 nation=e.code, how=_how(world, e.route, nations),
                                 stage=e.stage, pot=e.pot, position=e.position)
                        for e in entries),
                       key=lambda e: (e.position or 99, e.pot or 9, e.club.name)))


def summaries(conn: Connection, world: World) -> EuropeListOut:
    """This season's European competitions: the stage under way, and the user's club."""
    meta = read_meta(conn)
    out = []
    for comp in competitions_by_rank(world):
        detail = europe(conn, world, comp.key)
        user = meta.user_club_id
        mine = next((e for e in detail.entries if e.club.id == user), None)
        out.append(EuropeSummaryOut(
            key=comp.key, name=comp.name, short_name=comp.short_name,
            stage=_stage_now(detail), user_status=_user_status(detail, user, mine),
            winner=detail.winner))
    has_any = bool(conn.execute(select(continental_entry.c.id)).first())
    return EuropeListOut(enabled=world.defs.europe.enabled or has_any, competitions=out)


def _stage_now(detail: EuropeOut) -> str | None:
    if detail.winner is not None:
        return f"Won by {detail.winner.name}"
    for rnd in reversed(detail.knockout):
        if rnd.drawn:
            return rnd.name
    phase = detail.league_phase
    if phase.drawn:
        played = max((md.round for md in phase.matchdays
                      if md.fixtures and all(f.status == "played" for f in md.fixtures)),
                     default=0)
        return ("League phase over" if phase.final
                else f"League phase, matchday {min(played + 1, phase.matches)} of {phase.matches}")
    if detail.qualifying.drawn:
        return detail.qualifying.name
    return None


def _user_status(detail: EuropeOut, user: int | None, mine: EntryOut | None) -> str | None:
    if user is None:
        return None
    rounds = [detail.qualifying, *detail.knockout]
    in_ties = [(rnd, t) for rnd in rounds for t in rnd.ties
               if user in (t.home.id, t.away.id if t.away else None)]
    if detail.winner is not None and detail.winner.id == user:
        return "Winners"
    if in_ties:
        rnd, tie = in_ties[-1]
        if tie.winner is not None and tie.winner.id != user:
            return f"Out in the {rnd.name.lower()}"
    if mine is None:
        return None
    if mine.position is not None:
        if mine.position > detail.league_phase.to_playoff[1]:
            return f"Out: {ordinal(mine.position)} in the league phase"
        if in_ties:
            return f"In the {in_ties[-1][0].name.lower()}"
        return f"{ordinal(mine.position)} in the league phase"
    if mine.stage == "qualifying":
        return f"In the {detail.qualifying.name.lower()}"
    row = next((r for r in detail.league_phase.table if r.club.id == user), None)
    return f"In the league phase: {ordinal(row.position)}" if row else "In the league phase"


@router.get("/europe")
def europe_list(session: Session) -> EuropeListOut:
    with session.read() as conn:
        return summaries(conn, get_world())


@router.get("/europe/{key}")
def europe_detail(key: str, session: Session, season: int | None = None) -> EuropeOut:
    world = get_world()
    if key not in world.defs.continental:
        raise HTTPException(404, f"no competition {key}")
    with session.read() as conn:
        return europe(conn, world, key, season)
