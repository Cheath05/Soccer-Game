"""The orders a European season's places go in (W6, W7): a country's clubs (its top league's last
table; in the first season the real table of the season before, europe/season_before.yaml, then
its clubs by reputation; by reputation for a league new to the career; a
reputation-weighted lottery for a country with clubs in the world but no league in the game,
europe/settings.yaml lottery_power), and who won last season's cups and European finals. The
places themselves are handed out in places.py."""

import numpy as np
from sqlalchemy import Connection, select

from footsim.core.rng import derive_rng
from footsim.persistence.schema import (
    club,
    club_league_membership,
    competition,
    cup_tie,
    league_final,
    nation,
)
from footsim.world.context import World
from footsim.world.europe.common import KNOCKOUT
from footsim.world.meta import CareerMeta


def _top_league_key(world: World, nation_code: str) -> str | None:
    return next((key for key, lg in world.defs.leagues.items()
                 if lg.nation == nation_code and lg.tier == 1), None)


def nation_order(conn: Connection, world: World, meta: CareerMeta, season_id: int,
                 nation_code: str) -> list[int]:
    """The country's clubs in the order its places go: last season's top-league table, its
    clubs by reputation when there's no table yet, or a lottery when the country has no league
    in the career."""
    key = _top_league_key(world, nation_code)
    comp = (conn.execute(select(competition.c.id).where(competition.c.key == key)).first()
            if key is not None else None)
    if comp is not None:
        table = [r.club_id for r in conn.execute(select(league_final).where(
            league_final.c.season_id == season_id - 1,
            league_final.c.competition_id == comp.id).order_by(league_final.c.position))]
        if table:
            return table
        clubs = [r.id for r in conn.execute(
            select(club.c.id).join(club_league_membership,
                                   club_league_membership.c.club_id == club.c.id)
            .where(club_league_membership.c.season_id == season_id,
                   club_league_membership.c.competition_id == comp.id)
            .order_by(club.c.reputation.desc(), club.c.id))]
        before = _before_table(conn, world, season_id, nation_code)
        return [c for c in before if c in clubs] + [c for c in clubs if c not in before]
    before = _before_table(conn, world, season_id, nation_code)
    return before + [c for c in _lottery(conn, world, meta, season_id, nation_code)
                     if c not in before]


def _club_id(conn: Connection, nation_code: str, name: str) -> int | None:
    """A club of a country by its name in the game."""
    row = conn.execute(select(club.c.id).join(nation, nation.c.id == club.c.nation_id).where(
        nation.c.code == nation_code, club.c.name == name).order_by(club.c.id)).first()
    return int(row.id) if row is not None else None


def _before_table(conn: Connection, world: World, season_id: int, nation_code: str) -> list[int]:
    """In a career's first season, its country's real final table of the season before
    (europe/season_before.yaml), the clubs in the game; otherwise nothing."""
    before = world.defs.season_before.countries.get(nation_code)
    if season_id != 1 or before is None:
        return []
    found = [_club_id(conn, nation_code, name) for name in before.table]
    return [c for c in dict.fromkeys(found) if c is not None]


def _lottery(conn: Connection, world: World, meta: CareerMeta, season_id: int,
             nation_code: str) -> list[int]:
    """A country without a league: its clubs (those in no league this season) in a weighted
    lottery order, each draw's chances weighted by reputation ** lottery_power."""
    in_league = select(club_league_membership.c.club_id).where(
        club_league_membership.c.season_id == season_id)
    rows = conn.execute(select(club.c.id, club.c.reputation).join(
        nation, nation.c.id == club.c.nation_id).where(
        nation.c.code == nation_code, club.c.id.not_in(in_league)).order_by(club.c.id)).all()
    if not rows:
        return []
    top = max(max(r.reputation for r in rows), 1)
    weights = np.array([(max(r.reputation, 1) / top) ** world.defs.europe.lottery_power
                        for r in rows])
    rng = derive_rng(meta.seed, "europe-lottery", season_id, nation_code)
    # Weighted sampling without replacement (Efraimidis and Spirakis): sort by u ** (1 / w).
    keys = np.log(rng.random(len(rows))) / weights
    return [rows[k].id for k in np.argsort(-keys, kind="stable")]


def _final_winner(conn: Connection, season_id: int, competition_key: str,
                  final_round: int) -> int | None:
    row = conn.execute(select(cup_tie.c.winner_club_id).join(
        competition, competition.c.id == cup_tie.c.competition_id).where(
        competition.c.key == competition_key, cup_tie.c.season_id == season_id,
        cup_tie.c.round == final_round, cup_tie.c.winner_club_id.is_not(None))).first()
    return int(row.winner_club_id) if row is not None else None


def cup_winner(conn: Connection, world: World, season_id: int, cup_key: str) -> int | None:
    """Who won a domestic cup's final in season ``season_id`` (the season before the career:
    as it really went)."""
    cup = world.defs.cups.get(cup_key)
    if cup is None:
        return None
    if season_id == 0:
        name = world.defs.season_before.countries.get(cup.nation, None)
        winner = name.cups.get(cup_key) if name is not None else None
        return _club_id(conn, cup.nation, winner) if winner else None
    return _final_winner(conn, season_id, cup_key, len(cup.rounds) - 1)


def holder(conn: Connection, world: World, season_id: int, comp_key: str) -> int | None:
    """Who won a European competition's final in season ``season_id`` (the season before the
    career: as it really went)."""
    if season_id == 0:
        before = world.defs.season_before.holders.get(comp_key)
        return _club_id(conn, before.nation, before.club) if before is not None else None
    comp = world.defs.continental[comp_key]
    return _final_winner(conn, season_id, comp_key, KNOCKOUT + len(comp.knockout) - 1)


def route_nation(world: World, route: str) -> str | None:
    """The country whose place a route is: league:ENG:4 and fill:ENG are England's, cup:FA_CUP
    the cup's country's; a holder's is its league's (None here)."""
    kind, _, rest = route.partition(":")
    if kind in ("league", "fill"):
        return rest.partition(":")[0] or None
    if kind == "cup":
        cup = world.defs.cups.get(rest)
        return cup.nation if cup else None
    return None
