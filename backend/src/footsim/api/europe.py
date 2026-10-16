"""The European competitions' pages (W6 E7): what's on this season, and each competition's
qualifying round, league-phase table and matchdays, and knockout rounds. Presentation only:
the rules are in world/europe/."""

from collections import defaultdict
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import Connection, Row, select

from footsim.api.queries import _club_names, _competitions, _season_label, fixtures_out
from footsim.api.routes import Session
from footsim.api.schemas import ClubRef, CupRoundOut, CupTieOut, FixtureOut, TableRowOut
from footsim.core.text import ordinal
from footsim.defs.europe import ContinentalDef
from footsim.persistence.schema import (
    club,
    club_coefficient,
    club_league_membership,
    competition,
    continental_entry,
    cup_tie,
    fixture,
    nation,
)
from footsim.world.context import World, get_world
from footsim.world.europe.coefficients import club_nations, coefficients
from footsim.world.europe.common import (
    KNOCKOUT,
    LEAGUE_PHASE,
    QUALIFYING,
    competitions_by_rank,
    europe_calendar,
    qualifying_round,
    round_key,
    round_number,
)
from footsim.world.europe.league_phase import table
from footsim.world.europe.places import ROUND_ORDER
from footsim.world.europe.qualifying import node_of, nodes, round_name
from footsim.world.europe.ranking import (
    club_associations,
    club_season_points,
    first_season_label,
    ranking,
    season_label_of,
)
from footsim.world.meta import read_meta

router = APIRouter(prefix="/api")


class EntryOut(BaseModel):
    club: ClubRef
    nation: str
    how: str  # how it got its place: "4th in the Premier League", "FA Cup winners"...
    stage: str  # qualifying | league_phase | out
    pot: int | None
    position: int | None
    round: str | None = None  # where it is: Q1, Q2, Q3, PO, or LP
    path: str | None = None  # champions, league or main, before the league phase
    entered: str | None = None  # where it started: "Second qualifying round (Champions Path)"
    came_from: str | None = None  # "From the Champions League third qualifying round"


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
    qualifying: CupRoundOut  # the latest qualifying round drawn (the first before any is)
    qualifying_rounds: list[CupRoundOut]  # every qualifying round and path, first round first
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


class NationOut(BaseModel):
    """A country with a league or a cup in the game, for the pickers: its continent and its
    place in the order they're listed (UEFA's ranking first, then the other continents' by
    their top league's money)."""

    code: str
    name: str
    confederation: str  # UEFA, AFC, CONCACAF...
    continent: str  # Europe, Asia, North America...
    rank: int  # 1 is listed first
    uefa_rank: int | None  # its place in UEFA's country ranking, for a UEFA country
    featured: bool  # the big five: always within one tap


class CountryCoefficientOut(BaseModel):
    rank: int
    nation: str
    name: str
    seasons: list[float]  # the five seasons, oldest first (the last may be in progress)
    total: float


class ClubCoefficientOut(BaseModel):
    rank: int
    club: ClubRef
    nation: str
    coefficient: float


class RankingsOut(BaseModel):
    season_labels: list[str]  # the five seasons' labels, oldest first
    in_progress: bool  # the last season is still being played (its figures so far)
    countries: list[CountryCoefficientOut]
    clubs: list[ClubCoefficientOut]  # the best 100 by the coefficient this season's draws use


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
    if kind == "eps":
        code, _, rank = rest.partition(":")
        return f"{_how(world, f'league:{code}:{rank}', nations)} (a European Performance Spot)"
    if kind == "fill":
        return f"An extra place for {nations.get(rest, rest)}"
    if kind == "dropped":
        comp = world.defs.continental.get(rest)
        return f"From the {comp.name} play-off round" if comp else "From qualifying"
    return route


def _node_words(world: World, text: str | None) -> str | None:
    """A stored round (UCL:Q2:champions) in words: "Champions League second qualifying round
    (Champions Path)"."""
    if not text:
        return None
    node = node_of(text)
    comp = world.defs.continental.get(node.competition)
    if comp is None:
        return None
    if node.round == LEAGUE_PHASE:
        return f"{comp.short_name} league phase"
    return f"{comp.short_name} {round_name(world, node)[:1].lower()}{round_name(world, node)[1:]}"


def _rounds(world: World, comp: ContinentalDef, comp_id: int | None, season_id: int,
            conn: Connection, names: dict[int, str], comps: dict[int, Row[Any]]
            ) -> tuple[list[CupRoundOut], list[CupRoundOut], list[FixtureOut]]:
    ties = (conn.execute(select(cup_tie).where(
        cup_tie.c.season_id == season_id, cup_tie.c.competition_id == comp_id)
        .order_by(cup_tie.c.round, cup_tie.c.id)).all() if comp_id is not None else [])
    games: dict[tuple[int, str | None], list[FixtureOut]] = defaultdict(list)
    phase_games: list[FixtureOut] = []
    if comp_id is not None:
        rows = conn.execute(select(fixture).where(
            fixture.c.season_id == season_id, fixture.c.competition_id == comp_id)
            .order_by(fixture.c.round, fixture.c.leg, fixture.c.date, fixture.c.id)).all()
        for row, out in zip(rows, fixtures_out(conn, rows, names, comps), strict=True):
            if QUALIFYING < row.round < KNOCKOUT:
                phase_games.append(out)
            else:
                games[(row.round, row.tie)].append(out)
    dates = europe_calendar(world, season_id).competitions[comp.key]

    def ref(club_id: int | None) -> ClubRef | None:
        return ClubRef(id=club_id, name=names[club_id]) if club_id else None

    def round_out(index: int, number: int, name: str, legs: int, days: list[list[date]],
                  path: str | None = None) -> CupRoundOut:
        in_round = [t for t in ties if t.round == number and (path is None or t.path == path)]
        return CupRoundOut(
            index=index, name=name, dates=[min(leg).isoformat() for leg in days], legs=legs,
            drawn=bool(in_round), round=round_key(number) if number <= QUALIFYING else None,
            path=path,
            ties=[CupTieOut(tie=t.tie, home=ClubRef(id=t.club_a_id, name=names[t.club_a_id]),
                            away=ref(t.club_b_id), fixtures=games.get((number, t.tie), []),
                            winner=ref(t.winner_club_id)) for t in in_round])

    qualifying = [round_out(k, round_number(node.round), round_name(world, node),
                            qualifying_round(comp, round_number(node.round)).legs,
                            dates.qualifying[node.round], node.path)
                  for k, node in enumerate(n for n in nodes(world) if n.competition == comp.key)]
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
    qualifying_rounds, knockout, phase_games = _rounds(world, comp, comp_id, season_id, conn,
                                                       names, comps)
    drawn = [r for r in qualifying_rounds if r.drawn]
    qualifying = drawn[-1] if drawn else qualifying_rounds[0]
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
        qualifying_rounds=qualifying_rounds, league_phase=league_phase, knockout=knockout,
        winner=winner,
        entries=sorted((EntryOut(club=ClubRef(id=e.club_id, name=names[e.club_id]),
                                 nation=e.code, how=_how(world, e.route, nations),
                                 stage=e.stage, pot=e.pot, position=e.position,
                                 round=(round_key(e.entry_round) if e.entry_round is not None
                                        else None),
                                 path=e.path, entered=_node_words(world, e.entered),
                                 came_from=(f"From the {_node_words(world, e.came_from)}"
                                            if e.came_from else None))
                        for e in entries),
                       key=lambda e: (e.stage == "out", e.position or 99, e.pot or 9,
                                      ROUND_ORDER.get(e.round or "", 9), e.club.name)))


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


def _round_words(detail: EuropeOut, mine: EntryOut) -> str:
    """The qualifying round a club is in, in words."""
    found = next((r for r in detail.qualifying_rounds
                  if r.round == mine.round and r.path == mine.path), None)
    return found.name.lower() if found else "qualifying"


def _user_status(detail: EuropeOut, user: int | None, mine: EntryOut | None) -> str | None:
    if user is None:
        return None
    rounds = [*detail.qualifying_rounds, *detail.knockout]
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
        return f"In the {_round_words(detail, mine)}"
    if mine.stage == "out":
        return "Out in qualifying"
    row = next((r for r in detail.league_phase.table if r.club.id == user), None)
    return f"In the league phase: {ordinal(row.position)}" if row else "In the league phase"


@router.get("/europe")
def europe_list(session: Session) -> EuropeListOut:
    with session.read() as conn:
        return summaries(conn, get_world())




CONTINENTS = {"UEFA": "Europe", "AFC": "Asia", "CONCACAF": "North America",
              "CONMEBOL": "South America", "CAF": "Africa", "OFC": "Oceania"}
BIG_FIVE = ("ENG", "ESP", "ITA", "GER", "FRA")


def nations_out(conn: Connection | None, world: World) -> list[NationOut]:
    """Every country with a league or a cup, UEFA's in its ranking order (the career's, or the
    real one before a career), then the rest by their top league's money."""
    through = read_meta(conn).season_id - 1 if conn is not None else 0
    uefa = {r.nation: r.rank for r in ranking(conn, world, through)}
    codes = ({lg.nation for lg in world.defs.leagues.values()}
             | {cup.nation for cup in world.defs.cups.values()})
    income = {lg.nation: world.defs.finance.league_income.get(key) for key, lg in
              world.defs.leagues.items() if lg.tier == 1}

    def order(code: str) -> tuple[int, float, str]:
        if code in uefa:
            return (0, uefa[code], code)
        money = income.get(code)
        return (1, -(money.base if money else 0.0), code)

    out = []
    for k, code in enumerate(sorted(codes, key=order), start=1):
        n = world.defs.nations.get(code)
        confederation = n.confederation if n else ""
        out.append(NationOut(code=code, name=n.name if n else code, confederation=confederation,
                             continent=CONTINENTS.get(confederation, confederation), rank=k,
                             uefa_rank=uefa.get(code), featured=code in BIG_FIVE))
    return out


def rankings(conn: Connection, world: World) -> RankingsOut:
    """UEFA's country and club rankings as they stand: five seasons to this one, this one's
    figures so far until its last final is decided."""
    meta = read_meta(conn)
    rules = world.defs.europe.coefficient
    recorded = conn.execute(select(club_coefficient.c.club_id).where(
        club_coefficient.c.season_id == meta.season_id)).first() is not None
    live: dict[str, float] = {}
    club_live: dict[int, float] = {}
    if not recorded:
        club_live = club_season_points(conn, world, meta.season_id)
        countries = club_associations(conn, meta.season_id, sorted(club_live))
        by_country: dict[str, list[float]] = defaultdict(list)
        for club_id, p in club_live.items():
            if club_id in countries:
                by_country[countries[club_id]].append(p)
        live = {code: sum(v) / len(v) for code, v in by_country.items()}
    table: list[tuple[str, list[float]]] = [
        (r.nation, r.seasons if recorded else [*r.seasons[:-1], live.get(r.nation, 0.0)])
        for r in ranking(conn, world, meta.season_id)]
    if not recorded:  # this season's figures so far, in place of the (empty) recorded ones
        table.sort(key=lambda r: (-round(sum(r[1]), 3),
                                  *(-round(v, 3) for v in reversed(r[1])), r[0]))
    countries_out = [(k, code, values) for k, (code, values) in enumerate(table, start=1)]
    first = first_season_label(conn, world)
    labels = [season_label_of(s, first)
              for s in range(meta.season_id - rules.seasons + 1, meta.season_id + 1)]
    names: dict[str, str] = {code: n.name for code, n in world.defs.nations.items()}
    # Clubs: the coefficients this season's draws use (the five seasons before it, reputation
    # standing in for those before the career, UEFA's floor), for every club in a UEFA
    # country's league this season or in Europe.
    uefa = {code for code, n in world.defs.nations.items() if n.confederation == "UEFA"}
    in_leagues = {r.club_id for r in conn.execute(
        select(club_league_membership.c.club_id).join(
            competition, competition.c.id == club_league_membership.c.competition_id).join(
            nation, nation.c.id == competition.c.nation_id).where(
            club_league_membership.c.season_id == meta.season_id, nation.c.code.in_(uefa)))}
    in_europe = {r.club_id for r in conn.execute(select(continental_entry.c.club_id).where(
        continental_entry.c.season_id == meta.season_id))}
    ids = sorted(in_leagues | in_europe)
    coefficient = coefficients(conn, world, ids, meta.season_id)
    club_codes = club_nations(conn, ids, meta.season_id)
    best = sorted(ids, key=lambda c: (-coefficient[c], c))[:100]
    club_names = _club_names(conn)
    return RankingsOut(
        season_labels=labels, in_progress=not recorded,
        countries=[CountryCoefficientOut(rank=k, nation=code, name=names.get(code, code),
                                         seasons=[round(v, 3) for v in values],
                                         total=round(sum(values), 3))
                   for k, code, values in countries_out],
        clubs=[ClubCoefficientOut(rank=k, club=ClubRef(id=c, name=club_names[c]),
                                  nation=club_codes.get(c, ""),
                                  coefficient=round(coefficient[c], 3))
               for k, c in enumerate(best, start=1)])


@router.get("/world/nations")
def world_nations(session: Session) -> list[NationOut]:
    world = get_world()
    if not session.active:
        return nations_out(None, world)
    with session.read() as conn:
        return nations_out(conn, world)


@router.get("/europe/rankings")
def europe_rankings(session: Session) -> RankingsOut:
    with session.read() as conn:
        return rankings(conn, get_world())


# Last: "/europe/{key}" would otherwise catch "/europe/rankings".
@router.get("/europe/{key}")
def europe_detail(key: str, session: Session, season: int | None = None) -> EuropeOut:
    world = get_world()
    if key not in world.defs.continental:
        raise HTTPException(404, f"no competition {key}")
    with session.read() as conn:
        return europe(conn, world, key, season)
