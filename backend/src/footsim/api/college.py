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
from footsim.world.college.common import LOWER_PREFIX, NCAA, conference_event, is_lower_stage
from footsim.world.college.draft import draft_pool
from footsim.world.college.lower import Standing
from footsim.world.college.lower import competitions as lower_competitions
from footsim.world.college.season import (
    Record,
    bracket,
    college_competition,
    conference_tables,
    overall_records,
    rankings,
)
from footsim.world.context import World, get_world
from footsim.world.meta import CareerMeta, read_meta

router = APIRouter(prefix="/api/college")


class RecordOut(BaseModel):
    """A team's record over every college game this season: conference, non-conference and
    tournaments (a shoot-out counts as a draw)."""

    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int


def _record(rec: Record | None) -> RecordOut:
    rec = rec or Record()
    return RecordOut(played=rec.played, won=rec.won, drawn=rec.drawn, lost=rec.lost,
                     goals_for=rec.goals_for, goals_against=rec.goals_against)


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
    overall: RecordOut  # every college game this season, not only the conference's


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
    overall: RecordOut


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
def conferences(session: Session, season_id: int | None = None, division: int = 1
                ) -> list[ConferenceOut]:
    """Every conference's table (conference games only) and its champions so far; ``division``
    2 or 3 for D-II or D-III (W9e)."""
    world = get_world()
    if division != 1:
        return _lower_conferences(session, world, division, season_id)
    with session.read() as conn:
        meta = read_meta(conn)
        comp = _competition(conn, world)
        sid, _, _ = _season(conn, meta, season_id)
        names = _names(conn)
        titles = {(str(r.phase), str(r.kind)): int(r.club_id) for r in conn.execute(
            select(league_title).where(league_title.c.season_id == sid,
                                       league_title.c.competition_id == comp))}
        records = overall_records(conn, world, sid)
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
                    in_tournament=r.position <= places, overall=_record(records.get(r.club_id)))
                    for r in table]))
        return out


@router.get("/rankings")
def college_rankings(session: Session, limit: int = 50, division: int = 1) -> list[RankingOut]:
    """This season's RPI so far, best first; ``division`` 2 or 3 for D-II or D-III's (22 Nov)."""
    world = get_world()
    if division != 1:
        return _lower_rankings(session, world, division, limit)
    with session.read() as conn:
        meta = read_meta(conn)
        _competition(conn, world)
        names = _names(conn)
        conference = {int(r.club_id): str(r.conference)
                      for r in conn.execute(select(college_team))}
        ratings = rankings(conn, world, meta.season_id)
        records = overall_records(conn, world, meta.season_id)
        order = sorted(ratings, key=lambda c: (-ratings[c], c))[:max(1, limit)]
        return [RankingOut(rank=k, club=ClubRef(id=c, name=names[c]),
                           conference=world.defs.college.conferences[conference[c]].short_name,
                           rpi=round(ratings[c], 4), overall=_record(records.get(c)))
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
    if is_lower_stage(event):
        return _lower_bracket(session, world, event, season_id)
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


class TopRankOut(BaseModel):
    club_id: int
    rank: int
    division: int  # 1, 2 or 3: a D-II team's "#3" is D-II's third


@router.get("/top25")
def college_top25(session: Session) -> list[TopRankOut]:
    """The 25 best college programs of each division by this season's RPI (last season's final
    one until this season's games begin), for the "#12" beside their names. Empty without the
    NCAA."""
    from footsim.world.college import lower

    world = get_world()
    with session.read() as conn:
        meta = read_meta(conn)
        if college_competition(conn, world) is None:
            return []
        ratings = rankings(conn, world, meta.season_id)
        if not ratings and meta.season_id > 1:
            ratings = rankings(conn, world, meta.season_id - 1)
        order = sorted(ratings, key=lambda c: (-ratings[c], c))[:25]
        out = [TopRankOut(club_id=c, rank=k, division=1) for k, c in enumerate(order, start=1)]
        for division in sorted(lower.competitions(conn, world)):
            found = lower.ranking(conn, world, division, meta.season_id)
            if not found and meta.season_id > 1:
                found = lower.ranking(conn, world, division, meta.season_id - 1)
            out += [TopRankOut(club_id=c, rank=k, division=division)
                    for k, c in enumerate(found[:25], start=1)]
        return out


def _standing(r: Standing | None) -> RecordOut:
    """A lower-division team's record (none yet: all zeros)."""
    if r is None:
        return RecordOut(played=0, won=0, drawn=0, lost=0, goals_for=0, goals_against=0)
    return RecordOut(played=r.played, won=r.won, drawn=r.drawn, lost=r.lost,
                     goals_for=r.goals_for, goals_against=r.goals_against)


def _lower_rankings(session: Session, world: World, division: int, limit: int
                    ) -> list[RankingOut]:
    """A D-II/D-III division's RPI so far, best first."""
    from footsim.persistence.schema import lower_team
    from footsim.world.college import lower

    defs = lower.rules(world)
    if defs is None or division not in defs.divisions:
        raise HTTPException(404, "no such division")
    d = defs.divisions[division]
    with session.read() as conn:
        meta = read_meta(conn)
        if division not in lower.competitions(conn, world):
            raise HTTPException(404, "the lower divisions start next season")
        ratings = lower.rpi_ratings(conn, world, division, meta.season_id)
        found = lower.records(conn, world, division, meta.season_id)
        order = lower.ranking(conn, world, division, meta.season_id)[:max(1, limit)]
        names = {int(r.id): str(r.name) for r in conn.execute(
            select(club.c.id, club.c.name).where(club.c.id.in_(order)))}
        conference = {int(r.club_id): str(r.conference) for r in conn.execute(
            select(lower_team).where(lower_team.c.division == division))}

        return [RankingOut(rank=k, club=ClubRef(id=c, name=names[c]),
                           conference=d.conferences[conference[c]].short_name,
                           rpi=round(ratings[c], 4), overall=_standing(found.get(c)))
                for k, c in enumerate(order, start=1)]



def _lower_conferences(session: Session, world: World, division: int, season_id: int | None
                       ) -> list[ConferenceOut]:
    from footsim.world.college import lower

    defs = lower.rules(world)
    if defs is None or division not in defs.divisions:
        raise HTTPException(404, "no such division")
    with session.read() as conn:
        meta = read_meta(conn)
        comp = lower.competitions(conn, world).get(division)
        if comp is None:
            raise HTTPException(404, "the lower divisions start next season")
        sid, _, _ = _season(conn, meta, season_id)
        names = {int(r.id): str(r.name) for r in conn.execute(select(club.c.id, club.c.name))}
        titles = {str(r.phase): int(r.club_id) for r in conn.execute(
            select(league_title).where(league_title.c.season_id == sid,
                                       league_title.c.competition_id == comp,
                                       league_title.c.kind == "champion"))}
        found = lower.records(conn, world, division, sid)
        out = []
        for key, table in lower.conference_tables(conn, world, meta, division, sid).items():
            conf = defs.divisions[division].conferences[key]
            won = titles.get(key)

            out.append(ConferenceOut(
                key=key, name=conf.name, short_name=conf.short_name, tournament=0,
                regular_season_champion=ClubRef(id=won, name=names[won]) if won else None,
                tournament_champion=None,
                rows=[ConferenceRowOut(
                    position=r.position, club=ClubRef(id=r.club_id, name=names[r.club_id]),
                    played=r.played, won=r.won, drawn=r.drawn, lost=r.lost,
                    goals_for=r.goals_for, goals_against=r.goals_against, points=r.points,
                    in_tournament=r.position == 1 and conf.auto_bid,
                    overall=_standing(found.get(r.club_id))) for r in table]))
        return out


def _lower_bracket(session: Session, world: World, event: str, season_id: int | None
                   ) -> BracketOut:
    """A D-II/D-III national tournament's bracket (W9e)."""
    from footsim.persistence.schema import lower_team
    from footsim.world.college import lower

    defs = lower.rules(world)
    division = int(event.removeprefix(LOWER_PREFIX) or 0)
    if defs is None or division not in defs.divisions:
        raise HTTPException(404, "no such college tournament")
    d = defs.divisions[division]
    with session.read() as conn:
        meta = read_meta(conn)
        comp = lower.competitions(conn, world).get(division)
        if comp is None:
            raise HTTPException(404, "the lower divisions start next season")
        sid, label, start = _season(conn, meta, season_id)
        names = {int(r.id): str(r.name) for r in conn.execute(select(club.c.id, club.c.name))}
        conference = {int(r.club_id): str(r.conference)
                      for r in conn.execute(select(lower_team))}
        seeds, matches = bracket(conn, comp, sid, event)
        if not seeds:
            matches = []
        rows = {int(r.seed): r for r in conn.execute(select(college_entry).where(
            college_entry.c.season_id == sid, college_entry.c.event == event))}
        total = rounds_for(len(seeds)) if seeds else 0
        dates = d.tournament.rounds

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
            names_list = d.tournament.round_names
            rounds.append(BracketRoundOut(
                round=rnd, name=names_list[len(names_list) - total + rnd],
                date=day.isoformat(), matches=out))
        final = [m for m in matches if m.round == total - 1]
        winner = final[0].winner_seed if final and final[0].winner_seed else None
        return BracketOut(
            event=event, name=f"{d.short_name} Tournament", season=label,
            seeded=d.tournament.teams,
            entrants=[EntrantOut(
                seed=s, club=ClubRef(id=c, name=names[c]),
                conference=d.conferences[conference[c]].short_name,
                bid=rows[s].bid, rank=rows[s].rank, rpi=rows[s].rating)
                for s, c in sorted(seeds.items())],
            rounds=rounds,
            champion=ClubRef(id=seeds[winner], name=names[seeds[winner]]) if winner else None)


class AllDivisionEntrantOut(BaseModel):
    seed: int
    club: ClubRef
    division: int  # 1, 2 or 3
    division_name: str  # "D-I"
    rank: int  # in its division: 1 its national champion, then by the final RPI
    enters: str  # the round it starts in ("Round of 16": two byes)


class AllDivisionOut(BaseModel):
    name: str
    season: str
    selection: str  # the day the field is picked (ISO)
    entrants: list[AllDivisionEntrantOut]
    rounds: list[BracketRoundOut]  # every round; a round's matches once it's drawn
    champion: ClubRef | None
    champion_division: str | None


@router.get("/all-division")
def college_all_division(session: Session, season_id: int | None = None) -> AllDivisionOut:
    """The All-Division Tournament (22 Nov): D-I, D-II and D-III's best, after the national
    finals."""
    from footsim.world.college import all_division

    world = get_world()
    adt = all_division.rules(world)
    if adt is None:
        raise HTTPException(404, "no All-Division Tournament")
    with session.read() as conn:
        meta = read_meta(conn)
        if all_division.competition_id(conn, world) is None and not lower_competitions(
                conn, world):
            raise HTTPException(404, "the All-Division Tournament needs Divisions II and III")
        sid, label, start = _season(conn, meta, season_id)
        teams, matches = all_division.matches(conn, world, sid)
        names = {int(r.id): str(r.name) for r in conn.execute(
            select(club.c.id, club.c.name).where(club.c.id.in_([e.club_id for e in teams])))}

        def side(e: all_division.Entrant | None) -> BracketSideOut | None:
            if e is None:
                return None
            return BracketSideOut(seed=e.seed, club=ClubRef(id=e.club_id, name=names[e.club_id]))

        rounds = []
        for k, (when, name) in enumerate(zip(adt.rounds, adt.round_names, strict=True)):
            out = []
            for m in (m for m in matches if m.round == k):
                f = m.fixture
                out.append(BracketMatchOut(
                    index=m.index, a=side(m.a), b=side(m.b), bye=False, fixture_id=f.id,
                    date=f.date, neutral=bool(f.neutral), home_goals=f.home_goals,
                    away_goals=f.away_goals, home_pens=f.home_pens, away_pens=f.away_pens,
                    extra_time=bool(f.extra_time), home_club_id=f.home_club_id,
                    winner=side(m.winner)))
            rounds.append(BracketRoundOut(round=k, name=name, date=on(when, start).isoformat(),
                                          matches=out))
        final = [m for m in matches if m.round == len(adt.rounds) - 1 and m.winner is not None]
        won = final[0].winner if final else None
        return AllDivisionOut(
            name=adt.name, season=label, selection=on(adt.selection, start).isoformat(),
            entrants=[AllDivisionEntrantOut(
                seed=e.seed, club=ClubRef(id=e.club_id, name=names[e.club_id]),
                division=e.division, division_name=all_division.division_name(world, e.division),
                rank=e.rank, enters=adt.round_names[e.enters]) for e in teams],
            rounds=rounds,
            champion=ClubRef(id=won.club_id, name=names[won.club_id]) if won else None,
            champion_division=all_division.division_name(world, won.division) if won else None)
