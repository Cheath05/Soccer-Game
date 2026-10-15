"""A club's European record and its honours: how far it went in each European competition each
season, the trophies it has won (European, league and cup), and the Treble.

The Treble is a season's top league, its country's main domestic cup (the one whose winners take
the cup place in Europe, ``country_cup``) and the Champions League, all won by one club."""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, Row, or_, select

from footsim.api.schemas import CupRunOut, EuropeRunOut, TrophyOut
from footsim.core.text import ordinal
from footsim.defs.europe import ContinentalDef
from footsim.persistence.schema import (
    competition,
    continental_entry,
    cup_tie,
    league_final,
)
from footsim.world.context import World
from footsim.world.europe.access import cup_winner, holder
from footsim.world.europe.common import KNOCKOUT, competitions_by_rank, qualifying_round
from footsim.world.europe.places import country_cup
from footsim.world.europe.qualifying import node_of, round_name

_KIND_ORDER = {"europe": 0, "league": 1, "cup": 2}


@dataclass(frozen=True)
class Treble:
    club_id: int
    nation: str  # a nation code
    league: str  # the league's name
    cup: str
    europe: str  # the Champions League's name

    @property
    def trophies(self) -> list[str]:
        return [self.league, self.cup, self.europe]


def treble(conn: Connection, world: World, season_id: int) -> Treble | None:
    """The club that won the Treble in season ``season_id``, if any: the Champions League's
    winners, if they also won their country's top league and its main cup."""
    top = next(iter(competitions_by_rank(world)), None)
    if top is None or season_id < 1:
        return None
    winner = holder(conn, world, season_id, top.key)
    if winner is None:
        return None
    row = conn.execute(select(league_final.c.position, league_final.c.outcome, competition.c.key,
                              competition.c.name).join(
        competition, competition.c.id == league_final.c.competition_id).where(
        league_final.c.season_id == season_id, league_final.c.club_id == winner)).first()
    league = world.defs.leagues.get(row.key) if row is not None else None
    if row is None or league is None or league.tier != 1 or row.position != 1:
        return None
    cup_key = country_cup(world, league.nation)
    if cup_key is None or cup_winner(conn, world, season_id, cup_key) != winner:
        return None
    return Treble(winner, league.nation, row.name, world.defs.cups[cup_key].name, top.name)


def _result(club_id: int, tie: Row[Any]) -> str:
    """How the club did in a tie: won (a bye counts), lost or pending."""
    if tie.club_b_id is None or tie.winner_club_id == club_id:
        return "won"
    return "pending" if tie.winner_club_id is None else "lost"


def _run(world: World, comp: ContinentalDef, club_id: int, ties: list[Row[Any]],
         entry: Row[Any] | None) -> EuropeRunOut | None:
    """How far a club went in one competition's season, from its ties and its entry (the league
    phase has no ties of its own)."""
    def out(reached: str, *, won: bool = False, lost: bool = False, position: int | None = None
            ) -> EuropeRunOut:
        return EuropeRunOut(key=comp.key, name=comp.name, short_name=comp.short_name,
                            reached=reached, won=won, out=lost, position=position)

    knockout = [t for t in ties if t.round >= KNOCKOUT]
    if knockout:
        last = max(knockout, key=lambda t: t.round)
        index, result = last.round - KNOCKOUT, _result(club_id, last)
        if index == len(comp.knockout) - 1 and result == "won":
            return out("Winners", won=True)
        if result == "won":  # through to a round not drawn yet
            return out(comp.knockout[index + 1].name)
        return out(comp.knockout[index].name, lost=result == "lost")
    if entry is not None and (entry.stage == "league_phase" or entry.position is not None):
        position = entry.position
        reached = f"League phase ({ordinal(position)})" if position else "League phase"
        return out(reached, position=position,
                   lost=position is not None and position > comp.league_phase.to_playoff[1])
    qualifying = [t for t in ties if t.round <= 0]
    if qualifying:
        last = max(qualifying, key=lambda t: t.round)
        return out(qualifying_round(comp, last.round).name,
                   lost=_result(club_id, last) == "lost")
    if entry is not None and entry.stage == "qualifying":  # entered, not played yet
        if entry.entered:
            node = node_of(entry.entered)
            return out(round_name(world, node).split(" (")[0])
        return out("Qualifying")
    return None


def european_runs(conn: Connection, world: World, club_id: int) -> dict[int, list[EuropeRunOut]]:
    """Every season's European competitions of a club, the top competition first: the
    qualifying round it went out in, its league phase position, the knockout round it reached,
    or Winners."""
    comps = {r.id: world.defs.continental[r.key] for r in conn.execute(
        select(competition.c.id, competition.c.key).where(competition.c.type == "continental"))
        if r.key in world.defs.continental}
    if not comps:
        return {}
    by_comp: dict[tuple[int, int], list[Row[Any]]] = defaultdict(list)
    for t in conn.execute(select(cup_tie).where(
            cup_tie.c.competition_id.in_(list(comps)),
            or_(cup_tie.c.club_a_id == club_id, cup_tie.c.club_b_id == club_id))):
        by_comp[(t.season_id, t.competition_id)].append(t)
    entries = {e.season_id: e for e in conn.execute(select(continental_entry).where(
        continental_entry.c.club_id == club_id))}
    for e in entries.values():
        if e.competition_id in comps:
            by_comp.setdefault((e.season_id, e.competition_id), [])
    runs: dict[int, list[EuropeRunOut]] = defaultdict(list)
    for (season_id, comp_id), ties in sorted(
            by_comp.items(), key=lambda kv: (kv[0][0], comps[kv[0][1]].rank)):
        entry = entries.get(season_id)
        run = _run(world, comps[comp_id], club_id, ties,
                   entry if entry is not None and entry.competition_id == comp_id else None)
        if run is not None:
            runs[season_id].append(run)
    return runs


def trophy_cabinet(world: World, labels: dict[int, str], titles: list[tuple[int, str, str]],
                   cups: dict[int, list[CupRunOut]], europe: dict[int, list[EuropeRunOut]]
                   ) -> list[TrophyOut]:
    """The honours by trophy, European first, then league titles, then cups; each with the
    seasons it was won, oldest first. ``titles``: (season id, league key, league name)."""
    won: dict[tuple[str, str], tuple[str, list[int]]] = {}

    def add(kind: str, key: str, name: str, season_id: int) -> None:
        won.setdefault((kind, key), (name, []))[1].append(season_id)

    for season_id, key, name in titles:
        add("league", key, name, season_id)
    for season_id, season_cups in cups.items():
        for cup_run in season_cups:
            if cup_run.won:
                add("cup", cup_run.key, cup_run.name, season_id)
    for season_id, season_europe in europe.items():
        for europe_run in season_europe:
            if europe_run.won:
                add("europe", europe_run.key, europe_run.name, season_id)

    def order(item: tuple[tuple[str, str], tuple[str, list[int]]]) -> tuple[int, int, str]:
        (kind, key), (name, _) = item
        rank = (world.defs.continental[key].rank if kind == "europe"
                else world.defs.leagues[key].tier if kind == "league" and key in world.defs.leagues
                else 0)
        return _KIND_ORDER[kind], rank, name

    return [TrophyOut(kind=kind, key=key, name=name,
                      seasons=[labels[s] for s in sorted(seasons)])
            for (kind, key), (name, seasons) in sorted(won.items(), key=order)]
