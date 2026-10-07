"""The season summary: how the season that has just ended went across the game (champions,
promotions and relegations), and for the user's squad (development, retirements, youth intake).

Built from the save after the rollover, not from the news messages, so it is the same however
the season ended. ``other_news`` keeps what the review doesn't cover out of those messages."""

import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from typing import Any

from sqlalchemy import Connection, Row, bindparam, func, select, text

from footsim.api import queries
from footsim.api.schemas import (
    ClubMoveOut,
    ClubRef,
    DevelopmentOut,
    HonourOut,
    PotentialOut,
    RetirementOut,
    SeasonFinalOut,
    SeasonReviewOut,
    YouthIntakeOut,
)
from footsim.importers.generate import age_on
from footsim.persistence.schema import (
    club_league_membership,
    competition,
    contract,
    cup_tie,
    league_final,
    player_season_overall,
    playoff_tie,
    season,
)
from footsim.scouting.estimates import OWN_CLUB_KNOWLEDGE, potential_label, potential_range
from footsim.world.context import World
from footsim.world.meta import read_meta
from footsim.world.overall_history import player_overalls, primary_positions
from footsim.world.squads import display_name

# News the season summary shows in its own sections (see world/season.py and lifecycle.py for
# where each is written), so the news list leaves them out.
_COVERED_NEWS = [re.compile(pattern) for pattern in (
    r"^Player development\. ",
    r"^The .+ season begins\.$",
    r" are .+ champions\.$",
    r" win the .+\.$",  # a play-off's or a cup's winners
    r" (promoted|relegated) to the .+\.$",
    r" retires at \d+\.$",
    r"^Youth intake: ",
)]


def other_news(messages: Iterable[str]) -> list[str]:
    """The news messages the season summary's sections don't already cover."""
    return [m for m in messages if not any(p.search(m) for p in _COVERED_NEWS)]


def _honours(conn: Connection, world: World, season_id: int, comps: dict[int, Row[Any]],
             names: dict[int, str]) -> list[HonourOut]:
    comp_ids = {c.key: cid for cid, c in comps.items()}

    def ref(club_id: int) -> ClubRef:
        return ClubRef(id=club_id, name=names[club_id])

    honours: list[HonourOut] = []
    for r in conn.execute(select(league_final).where(league_final.c.season_id == season_id,
                                                     league_final.c.position == 1)):
        comp = comps[r.competition_id]
        league = world.defs.leagues.get(comp.key)
        if league is not None:
            honours.append(HonourOut(kind="league", key=comp.key, name=comp.name,
                                     nation=league.nation, tier=league.tier,
                                     winner=ref(r.club_id)))
    for league in world.defs.leagues.values():
        for playoff in league.playoffs:
            if league.key not in comp_ids:
                continue
            final = conn.execute(select(playoff_tie.c.winner_club_id).where(
                playoff_tie.c.season_id == season_id,
                playoff_tie.c.competition_id == comp_ids[league.key],
                playoff_tie.c.playoff_key == playoff.key,
                playoff_tie.c.round == len(playoff.rounds) - 1,
                playoff_tie.c.winner_club_id.is_not(None))).first()
            if final is not None:
                honours.append(HonourOut(kind="playoff", key=playoff.key, name=playoff.name,
                                         nation=league.nation, tier=league.tier,
                                         winner=ref(final.winner_club_id)))
    for cup in world.defs.cups.values():
        if cup.key not in comp_ids:
            continue
        final = conn.execute(select(cup_tie.c.winner_club_id).where(
            cup_tie.c.season_id == season_id, cup_tie.c.competition_id == comp_ids[cup.key],
            cup_tie.c.round == len(cup.rounds) - 1,
            cup_tie.c.winner_club_id.is_not(None))).first()
        if final is not None:
            honours.append(HonourOut(kind="cup", key=cup.key, name=cup.name, nation=cup.nation,
                                     tier=0, winner=ref(final.winner_club_id)))
    order = {"league": 0, "playoff": 1, "cup": 2}
    return sorted(honours, key=lambda h: (h.nation != "ENG", h.nation, h.kind == "cup", h.tier,
                                          order[h.kind], h.key))


def _moves(conn: Connection, world: World, season_id: int, comps: dict[int, Row[Any]],
           names: dict[int, str]) -> tuple[list[ClubMoveOut], list[ClubMoveOut]]:
    """Clubs whose league changed from this season to the next: up (promoted) or down."""
    member: dict[int, dict[int, int]] = defaultdict(dict)
    for r in conn.execute(select(club_league_membership).where(
            club_league_membership.c.season_id.in_([season_id, season_id + 1]))):
        member[r.season_id][r.club_id] = r.competition_id
    finals = {(r.competition_id, r.club_id): r for r in conn.execute(
        select(league_final).where(league_final.c.season_id == season_id))}
    moves: list[tuple[bool, int, ClubMoveOut]] = []
    for club_id, old in member[season_id].items():
        new = member[season_id + 1].get(club_id)
        if new is None or new == old:
            continue
        final = finals.get((old, club_id))
        league = world.defs.leagues.get(comps[old].key)
        tier = comps[new].tier or 0
        up = tier < (comps[old].tier or 0)
        moves.append((up, tier, ClubMoveOut(
            club=ClubRef(id=club_id, name=names[club_id]), nation=league.nation if league else "",
            from_league=comps[old].name, to_league=comps[new].name,
            position=final.position if final else None,
            via_playoffs=bool(final and final.outcome == "playoff_winner"))))
    moves.sort(key=lambda m: (m[1], m[2].position or 0, m[2].club.name))
    return ([m for up, _, m in moves if up], [m for up, _, m in moves if not up])


def _development(conn: Connection, season_id: int, user: int, season_start: str, today: date
                 ) -> tuple[list[DevelopmentOut], bool, str | None]:
    """The user's players whose overall changed over the season, from the overalls recorded as
    it began and as the next one began. Also whether the season has any record, and the day
    it began being kept if that was after the start (a save upgraded mid-season)."""
    table = player_season_overall
    kept: str | None = conn.execute(select(func.min(table.c.recorded_on)).where(
        table.c.season_id == season_id)).scalar_one()
    if kept is None:
        return [], False, None
    since = kept if kept > season_start else None
    squad = [r.person_id for r in conn.execute(select(contract.c.person_id).where(
        contract.c.club_id == user, contract.c.is_active == 1))]
    overall: dict[int, dict[int, int]] = defaultdict(dict)
    for r in conn.execute(select(table).where(table.c.season_id.in_([season_id, season_id + 1]),
                                              table.c.player_id.in_(squad))):
        overall[r.season_id][r.player_id] = r.overall
    changed = [pid for pid, before in overall[season_id].items()
               if pid in overall[season_id + 1] and overall[season_id + 1][pid] != before]
    people = {r.id: r for r in conn.execute(text(
        "SELECT id, first_name, last_name, known_as, birth_date FROM person WHERE id IN :ids")
        .bindparams(bindparam("ids", expanding=True)), {"ids": changed or [0]})}
    positions = primary_positions(conn, changed)
    rows = [DevelopmentOut(
        player_id=pid, name=display_name(people[pid].first_name, people[pid].last_name,
                                         people[pid].known_as),
        position=positions.get(pid, "CM"),
        age=age_on(date.fromisoformat(people[pid].birth_date), today),
        before=overall[season_id][pid], after=overall[season_id + 1][pid],
        change=overall[season_id + 1][pid] - overall[season_id][pid]) for pid in changed]
    rows.sort(key=lambda d: (-d.change, d.name))
    return rows, True, since


def _retired(conn: Connection, world: World, day: str, user: int | None, names: dict[int, str]
             ) -> list[RetirementOut]:
    """Players who retired as the season ended: the user's, and other clubs' good ones."""
    people = conn.execute(text("""
        SELECT p.id, p.first_name, p.last_name, p.known_as, p.birth_date
        FROM person p JOIN player pl ON pl.person_id = p.id WHERE pl.retired_on = :day
    """), {"day": day}).all()
    if not people:
        return []
    ids = [p.id for p in people]
    clubs: dict[int, int] = {r.person_id: r.club_id for r in conn.execute(
        select(contract.c.person_id, contract.c.club_id).where(
            contract.c.end_date == day, contract.c.is_active == 0,
            contract.c.person_id.in_(ids)).order_by(contract.c.id))}
    overalls = player_overalls(conn, world, ids)
    positions = primary_positions(conn, ids)
    notable_from = world.defs.lifecycle.retirement.news_from
    retired = []
    for p in people:
        club_id = clubs.get(p.id)
        own = club_id is not None and club_id == user
        if own or (club_id is not None and overalls[p.id] >= notable_from):
            retired.append(RetirementOut(
                player_id=p.id, name=display_name(p.first_name, p.last_name, p.known_as),
                position=positions.get(p.id, "CM"),
                age=age_on(date.fromisoformat(p.birth_date), date.fromisoformat(day)),
                overall=overalls[p.id],
                club=ClubRef(id=club_id, name=names[club_id]) if club_id is not None else None,
                own_player=own))
    return sorted(retired, key=lambda r: (-r.overall, r.name))


def _youth(conn: Connection, world: World, day: str, user: int, seed: int) -> list[YouthIntakeOut]:
    """The youngsters who joined the user's academy as the season began, best prospect first."""
    rows = conn.execute(text("""
        SELECT p.id, p.first_name, p.last_name, p.known_as, p.birth_date, pl.pa_hidden
        FROM contract k JOIN person p ON p.id = k.person_id
        JOIN player pl ON pl.person_id = p.id
        WHERE k.club_id = :club AND k.kind = 'youth' AND k.start_date = :day
    """), {"club": user, "day": day}).all()
    ids = [r.id for r in rows]
    overalls = player_overalls(conn, world, ids)
    positions = primary_positions(conn, ids)
    youngsters = []
    for r in rows:
        age = age_on(date.fromisoformat(r.birth_date), date.fromisoformat(day))
        low, high = potential_range(r.pa_hidden, overalls[r.id], age, OWN_CLUB_KNOWLEDGE, seed,
                                    r.id)
        youngsters.append(YouthIntakeOut(
            player_id=r.id, name=display_name(r.first_name, r.last_name, r.known_as),
            position=positions.get(r.id, "CM"), age=age, overall=overalls[r.id],
            potential=PotentialOut(low=low, high=high, label=potential_label(high))))
    return sorted(youngsters, key=lambda y: (-y.potential.high, y.name))


def season_review(conn: Connection, world: World, season_id: int, user: int | None
                  ) -> SeasonReviewOut:
    """How ``season_id`` ended. The rollover into the next season has happened: its first day
    is when the retirements and the youth intake took place."""
    meta = read_meta(conn)
    seasons = {r.id: r for r in conn.execute(select(season))}
    following = seasons.get(season_id + 1)
    comps = queries._competitions(conn)
    names = queries._club_names(conn)
    promoted, relegated = _moves(conn, world, season_id, comps, names)
    development: list[DevelopmentOut] = []
    recorded, since = True, None
    if user is not None:
        development, recorded, since = _development(
            conn, season_id, user, seasons[season_id].start_date, meta.current_date)
    retired: list[RetirementOut] = []
    youth: list[YouthIntakeOut] = []
    if following is not None:
        retired = _retired(conn, world, following.start_date, user, names)
        if user is not None:
            youth = _youth(conn, world, following.start_date, user, meta.seed)
    return SeasonReviewOut(
        season=seasons[season_id].label, next_season=following.label if following else None,
        honours=_honours(conn, world, season_id, comps, names), promoted=promoted,
        relegated=relegated, development=development, development_recorded=recorded,
        development_since=since, retired=retired, youth=youth)


def season_final(conn: Connection, world: World, user: int, messages: Iterable[str] = ()
                 ) -> SeasonFinalOut | None:
    """How the user's club finished the season that has just ended, and the review of it."""
    ended = read_meta(conn).season_id - 1
    row = conn.execute(
        select(league_final, competition.c.name).join(
            competition, competition.c.id == league_final.c.competition_id).where(
            league_final.c.season_id == ended, league_final.c.club_id == user)).first()
    if row is None:
        return None
    return SeasonFinalOut(
        competition=row.name, position=row.position, played=row.played, won=row.won,
        drawn=row.drawn, lost=row.lost, goals_for=row.goals_for, goals_against=row.goals_against,
        points=row.points, outcome=row.outcome,
        cups=queries.cup_runs(conn, world, user).get(ended, []),
        review=season_review(conn, world, ended, user), news=other_news(messages))
