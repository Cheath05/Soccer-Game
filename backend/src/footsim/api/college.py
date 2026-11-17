"""US college soccer's read API (W9a, world/college/): the conference tables, the RPI, a
tournament's bracket (a conference's or the NCAA's) and the draft pool. Presentation only."""

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import Connection, select

from footsim.api.routes import Session
from footsim.api.schemas import ClubRef
from footsim.competitions.bracket import BYE, rounds_for
from footsim.defs.college import on
from footsim.persistence.schema import club, college_entry, college_team, league_title, season
from footsim.world.college.common import NCAA, conference_event
from footsim.world.college.draft import draft_pool
from footsim.world.college.season import (
    bracket,
    college_competition,
    conference_tables,
    rankings,
)
from footsim.world.context import World, get_world
from footsim.world.meta import CareerMeta, read_meta

router = APIRouter(prefix="/api/college")


class ConferenceRowOut(BaseModel):
    position: int
    club: ClubRef
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    points: int
    in_tournament: bool  # places in its conference tournament (or, with none, the title)


class ConferenceOut(BaseModel):
    key: str
    name: str
    short_name: str
    tournament: int  # teams in its tournament; 0: none
    regular_season_champion: ClubRef | None
    tournament_champion: ClubRef | None
    rows: list[ConferenceRowOut]


class RankingOut(BaseModel):
    rank: int
    club: ClubRef
    conference: str
    rpi: float


class BracketSideOut(BaseModel):
    seed: int
    club: ClubRef


class BracketMatchOut(BaseModel):
    index: int  # its place in the round, top to bottom
    a: BracketSideOut | None  # None: not decided yet
    b: BracketSideOut | None
    bye: bool  # a first-round bye: ``a`` goes straight through
    fixture_id: int | None
    date: str | None
    neutral: bool
    home_goals: int | None
    away_goals: int | None
    home_pens: int | None
    away_pens: int | None
    extra_time: bool
    home_club_id: int | None  # the home side (the better seed, unless neutral)
    winner: BracketSideOut | None


class BracketRoundOut(BaseModel):
    round: int
    name: str
    date: str
    matches: list[BracketMatchOut]


class EntrantOut(BaseModel):
    seed: int
    club: ClubRef
    conference: str
    bid: str | None  # auto | at_large (the NCAA)
    rank: int | None  # by the RPI, when the field was picked
    rpi: float | None


class BracketOut(BaseModel):
    event: str  # NCAA, or CT:<conference>
    name: str
    season: str
    seeded: int  # the NCAA's seeds (byes); a conference tournament's whole field
    entrants: list[EntrantOut]
    rounds: list[BracketRoundOut]
    champion: ClubRef | None


class ProspectOut(BaseModel):
    player_id: int
    name: str
    college: ClubRef
    class_year: str  # Fr, So, Jr, Sr
    age: int
    position: str
    overall: int
    potential: int
    ga: bool  # an underclassman who declared (Generation adidas)


def _season(conn: Connection, meta: CareerMeta, season_id: int | None) -> tuple[int, str, date]:
    sid = season_id or meta.season_id
    row = conn.execute(select(season).where(season.c.id == sid)).first()
    if row is None:
        raise HTTPException(404, "no such season")
    return sid, str(row.label), date.fromisoformat(str(row.start_date))


def _names(conn: Connection) -> dict[int, str]:
    return {int(r.id): str(r.name) for r in conn.execute(
        select(club.c.id, club.c.name).where(club.c.id.in_(select(college_team.c.club_id))))}


def _competition(conn: Connection, world: World) -> int:
    comp = college_competition(conn, world)
    if comp is None:
        raise HTTPException(404, "this career has no college soccer yet: it starts next season")
    return comp


@router.get("/conferences")
def conferences(session: Session, season_id: int | None = None) -> list[ConferenceOut]:
    """Every conference's table (conference games only) and its champions so far."""
    world = get_world()
    with session.read() as conn:
        meta = read_meta(conn)
        comp = _competition(conn, world)
        sid, _, _ = _season(conn, meta, season_id)
        names = _names(conn)
        titles = {(str(r.phase), str(r.kind)): int(r.club_id) for r in conn.execute(
            select(league_title).where(league_title.c.season_id == sid,
                                       league_title.c.competition_id == comp))}
        out = []
        for key, table in conference_tables(conn, world, meta, sid).items():
            conf = world.defs.college.conferences[key]
            regular = (titles.get((key, "award")) if conf.tournament >= 2
                       else titles.get((key, "champion")))
            won = titles.get((key, "champion")) if conf.tournament >= 2 else None
            places = conf.tournament if conf.tournament >= 2 else 1
            out.append(ConferenceOut(
                key=key, name=conf.name, short_name=conf.short_name, tournament=conf.tournament,
                regular_season_champion=ClubRef(id=regular, name=names[regular])
                if regular else None,
                tournament_champion=ClubRef(id=won, name=names[won]) if won else None,
                rows=[ConferenceRowOut(
                    position=r.position, club=ClubRef(id=r.club_id, name=names[r.club_id]),
                    played=r.played, won=r.won, drawn=r.drawn, lost=r.lost,
                    goals_for=r.goals_for, goals_against=r.goals_against, points=r.points,
                    in_tournament=r.position <= places) for r in table]))
        return out


@router.get("/rankings")
def college_rankings(session: Session, limit: int = 50) -> list[RankingOut]:
    """This season's RPI so far, best first."""
    world = get_world()
    with session.read() as conn:
        meta = read_meta(conn)
        _competition(conn, world)
        names = _names(conn)
        conference = {int(r.club_id): str(r.conference)
                      for r in conn.execute(select(college_team))}
        ratings = rankings(conn, world, meta.season_id)
        order = sorted(ratings, key=lambda c: (-ratings[c], c))[:max(1, limit)]
        return [RankingOut(rank=k, club=ClubRef(id=c, name=names[c]),
                           conference=world.defs.college.conferences[conference[c]].short_name,
                           rpi=round(ratings[c], 4))
                for k, c in enumerate(order, start=1)]


def _round_name(event: str, world: World, round_: int, total: int) -> str:
    if event == NCAA:
        return world.defs.college.rules.ncaa.round_names[round_]
    from_end = total - 1 - round_
    return (["Final", "Semifinals", "Quarterfinals"][from_end] if from_end < 3
            else "First round")


@router.get("/bracket")
def college_bracket(session: Session, event: str = NCAA,
                    season_id: int | None = None) -> BracketOut:
    """A tournament's bracket: ``NCAA`` (the default) or ``CT:<conference key>``."""
    world = get_world()
    college = world.defs.college
    prefix = conference_event("")
    if event != NCAA and not (event.startswith(prefix)
                              and event.removeprefix(prefix) in college.conferences):
        raise HTTPException(404, "no such college tournament")
    with session.read() as conn:
        meta = read_meta(conn)
        comp = _competition(conn, world)
        sid, label, start = _season(conn, meta, season_id)
        names = _names(conn)
        conference = {int(r.club_id): str(r.conference)
                      for r in conn.execute(select(college_team))}
        seeds, matches = bracket(conn, comp, sid, event)
        if not seeds:  # the field isn't picked yet: no rounds to show
            matches = []
        rows = {int(r.seed): r for r in conn.execute(select(college_entry).where(
            college_entry.c.season_id == sid, college_entry.c.event == event))}
        if event == NCAA:
            name, dates = "NCAA Tournament", college.rules.ncaa.rounds
            seeded = college.rules.ncaa.seeds
        else:
            conf = college.conferences[event.removeprefix(conference_event(""))]
            name = f"{conf.short_name} Tournament"
            dates, seeded = college.rules.conference_tournament.rounds, len(seeds)
        total = rounds_for(len(seeds)) if seeds else 0

        def side(seed: int | None) -> BracketSideOut | None:
            if seed is None or seed == BYE:
                return None
            return BracketSideOut(seed=seed, club=ClubRef(id=seeds[seed],
                                                          name=names[seeds[seed]]))

        rounds = []
        for rnd in range(total):
            day = on(dates[len(dates) - total + rnd], start)
            out = []
            for m in (m for m in matches if m.round == rnd):
                f = m.fixture
                out.append(BracketMatchOut(
                    index=m.index, a=side(m.seed_a), b=side(m.seed_b),
                    bye=rnd == 0 and m.seed_b == BYE, fixture_id=f.id if f else None,
                    date=f.date if f else None, neutral=bool(f.neutral) if f else False,
                    home_goals=f.home_goals if f else None,
                    away_goals=f.away_goals if f else None,
                    home_pens=f.home_pens if f else None, away_pens=f.away_pens if f else None,
                    extra_time=bool(f.extra_time) if f else False,
                    home_club_id=f.home_club_id if f else None, winner=side(m.winner_seed)))
            rounds.append(BracketRoundOut(round=rnd, name=_round_name(event, world, rnd, total),
                                          date=day.isoformat(), matches=out))
        final = [m for m in matches if m.round == total - 1]
        winner = final[0].winner_seed if final and final[0].winner_seed else None
        return BracketOut(
            event=event, name=name, season=label, seeded=seeded,
            entrants=[EntrantOut(
                seed=s, club=ClubRef(id=c, name=names[c]),
                conference=college.conferences[conference[c]].short_name,
                bid=rows[s].bid, rank=rows[s].rank, rpi=rows[s].rating)
                for s, c in sorted(seeds.items())],
            rounds=rounds,
            champion=ClubRef(id=seeds[winner], name=names[seeds[winner]]) if winner else None)


@router.get("/draft-pool")
def college_draft_pool(session: Session, season_id: int | None = None) -> list[ProspectOut]:
    """The season's draft prospects still to be picked, best first (declared after the College
    Cup; empty before it)."""
    world = get_world()
    with session.read() as conn:
        meta = read_meta(conn)
        sid, _, _ = _season(conn, meta, season_id)
        return [ProspectOut(player_id=p.player_id, name=p.name,
                            college=ClubRef(id=p.college_id, name=p.college),
                            class_year=p.class_year, age=p.age, position=p.position,
                            overall=p.overall, potential=p.potential, ga=p.ga)
                for p in draft_pool(conn, world, meta, sid)]
