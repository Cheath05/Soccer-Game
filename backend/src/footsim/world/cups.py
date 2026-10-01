"""Knockout cups through a season (data/config/cups/*.yaml, dates in the season calendar).

Each round is drawn once the one before it is over. Where a round sends more clubs through
than half of those in it, the highest-ranked are exempt (a bye). A club's league match within
two days of a cup match is moved to the nearest free day for both clubs, a midweek where
possible, as real fixture lists are rearranged; leagues a round ``blocks`` play nothing that
day in the first place."""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import Connection, Row, or_, select, update

from footsim.core.rng import derive_rng
from footsim.defs.calendar import SeasonCalendarDef
from footsim.defs.cups import CupDef
from footsim.match.report import Decider
from footsim.persistence.schema import (
    club,
    club_league_membership,
    competition,
    cup_tie,
    fixture,
    league_final,
)
from footsim.world.context import World
from footsim.world.meta import CareerMeta
from footsim.world.squads import club_name

REST_DAYS = 2  # clear days a club gets between two matches
MIDWEEK = (1, 2)  # Tuesday, Wednesday: where a rearranged match goes if it can


def cups_in(world: World, calendar: SeasonCalendarDef) -> list[CupDef]:
    """The cups this season's calendar has dates for."""
    return [world.defs.cups[key] for key in calendar.cups if key in world.defs.cups]


def blocked_dates(world: World, calendar: SeasonCalendarDef, league_key: str) -> set[date]:
    """Days a league plays nothing because a cup round has them (its ``blocks``)."""
    days: set[date] = set()
    for cup in cups_in(world, calendar):
        for rnd, legs in zip(cup.rounds, calendar.cups[cup.key], strict=True):
            if league_key in rnd.blocks:
                days.update(legs)
    return days


def competition_ids(conn: Connection, world: World, calendar: SeasonCalendarDef
                    ) -> dict[str, int]:
    """Each of the season's cups' competition rows, added the first time it's played."""
    rows = conn.execute(select(competition.c.id, competition.c.key, competition.c.nation_id))
    existing = {r.key: (r.id, r.nation_id) for r in rows}
    ids: dict[str, int] = {}
    for cup in cups_in(world, calendar):
        if cup.key not in existing:
            nation_id = next((nation for key, (_, nation) in existing.items()
                              if key in world.defs.leagues
                              and world.defs.leagues[key].nation == cup.nation), None)
            inserted = conn.execute(competition.insert().values(
                key=cup.key, name=cup.name, short_name=cup.short_name, nation_id=nation_id,
                type="cup", tier=None, sim_level="playable"))
            key = inserted.inserted_primary_key
            assert key is not None
            existing[cup.key] = (int(key[0]), nation_id)
        ids[cup.key] = existing[cup.key][0]
    return ids


def start_cups(conn: Connection, world: World, meta: CareerMeta,
               calendar: SeasonCalendarDef, today: date) -> list[str]:
    """Draw the first round of each of the season's cups."""
    messages: list[str] = []
    for cup in cups_in(world, calendar):
        messages += _draw(conn, world, meta, calendar, cup, 0, today)
    return messages


def progress_cups(conn: Connection, world: World, meta: CareerMeta,
                  calendar: SeasonCalendarDef, today: date) -> list[str]:
    """Settle the ties played so far, and draw the next round once a round is over."""
    messages: list[str] = []
    ids = {r.key: r.id for r in conn.execute(select(competition.c.id, competition.c.key))}
    for cup in cups_in(world, calendar):
        ties = _ties(conn, meta.season_id, ids[cup.key]) if cup.key in ids else []
        if not ties:
            # A save from before the cups, in a season whose first round is still to come:
            # start it now (its league matches are rearranged around the ties as usual).
            if today + timedelta(days=REST_DAYS) < calendar.cups[cup.key][0][0]:
                messages += _draw(conn, world, meta, calendar, cup, 0, today)
            continue
        current = max(t.round for t in ties)
        decided = []
        for t in ties:
            if t.round == current and t.winner_club_id is None:
                winner = _winner(conn, meta.season_id, cup.key, t)
                if winner is not None:
                    conn.execute(update(cup_tie).where(cup_tie.c.id == t.id)
                                 .values(winner_club_id=winner))
                    decided.append((t, winner))
        messages += _results_news(conn, meta, cup, current, decided)
        if any(t.round == current and t.winner_club_id is None
               for t in _ties(conn, meta.season_id, ids[cup.key])):
            continue
        if current + 1 < len(cup.rounds):
            messages += _draw(conn, world, meta, calendar, cup, current + 1, today)
        elif decided:
            messages.append(f"{club_name(conn, decided[0][1])} win the {cup.name}.")
    return messages


def cup_decider(conn: Connection, world: World, fx: Row[Any]) -> Decider | None:
    """Knockout rules for a cup fixture; None for a first leg."""
    rnd = world.defs.cups[fx.stage].rounds[fx.round]
    if rnd.legs == 1:
        return Decider(extra_time=rnd.extra_time, penalties=rnd.penalties)
    if fx.leg != 2:
        return None
    first = conn.execute(select(fixture).where(
        fixture.c.season_id == fx.season_id, fixture.c.stage == fx.stage,
        fixture.c.round == fx.round, fixture.c.tie == fx.tie, fixture.c.leg == 1)).one()
    prior = ((first.home_goals, first.away_goals) if first.home_club_id == fx.home_club_id
             else (first.away_goals, first.home_goals))
    return Decider(extra_time=rnd.extra_time, penalties=rnd.penalties, first_leg=prior)


def _ties(conn: Connection, season_id: int, competition_id: int) -> list[Row[Any]]:
    return list(conn.execute(select(cup_tie).where(
        cup_tie.c.season_id == season_id, cup_tie.c.competition_id == competition_id,
    ).order_by(cup_tie.c.round, cup_tie.c.id)).all())


def _winner(conn: Connection, season_id: int, cup_key: str, tie: Row[Any]) -> int | None:
    games = conn.execute(select(fixture).where(
        fixture.c.season_id == season_id, fixture.c.stage == cup_key,
        fixture.c.round == tie.round, fixture.c.tie == tie.tie,
    ).order_by(fixture.c.leg)).all()
    if not games or any(g.status != "played" for g in games):
        return None
    goals = {tie.club_a_id: 0, tie.club_b_id: 0}
    for g in games:
        goals[g.home_club_id] += g.home_goals
        goals[g.away_club_id] += g.away_goals
    if goals[tie.club_a_id] != goals[tie.club_b_id]:
        return int(tie.club_a_id if goals[tie.club_a_id] > goals[tie.club_b_id]
                   else tie.club_b_id)
    last = games[-1]
    if last.home_pens is None:
        return None
    return int(last.home_club_id if last.home_pens > last.away_pens else last.away_club_id)


def _standing(conn: Connection, world: World, season_id: int
              ) -> dict[int, tuple[int, int, int, int]]:
    """Each league club's place for exemptions and entry: its league's tier this season, then
    last season's tier and finish (promoted clubs below those who stayed up), then its
    reputation (all a first season has to go on)."""
    key_of = {r.id: r.key for r in conn.execute(select(competition.c.id, competition.c.key))}

    def tier(competition_id: int) -> int:
        return world.defs.leagues[key_of[competition_id]].tier

    now = {r.club_id: tier(r.competition_id) for r in conn.execute(
        select(club_league_membership).where(club_league_membership.c.season_id == season_id))
        if key_of[r.competition_id] in world.defs.leagues}
    last = {r.club_id: (tier(r.competition_id), r.position) for r in conn.execute(
        select(league_final).where(league_final.c.season_id == season_id - 1))
        if key_of[r.competition_id] in world.defs.leagues}
    reputation = {r.id: r.reputation for r in conn.execute(select(club.c.id, club.c.reputation))}
    return {c: (t, *last.get(c, (t, 99)), -reputation.get(c, 0)) for c, t in now.items()}


def _entrants(conn: Connection, cup: CupDef, round_index: int, season_id: int,
              standing: dict[int, tuple[int, int, int, int]]) -> list[int]:
    ids = {r.key: r.id for r in conn.execute(select(competition.c.id, competition.c.key))}
    clubs: list[int] = []
    for entry in cup.entering(round_index):
        members = [r.club_id for r in conn.execute(select(club_league_membership.c.club_id).where(
            club_league_membership.c.season_id == season_id,
            club_league_membership.c.competition_id == ids[entry.league]))]
        members.sort(key=lambda c: standing[c][1:])  # last season's finish within the league
        if entry.ranks is not None:
            members = members[entry.ranks[0] - 1:entry.ranks[1]]
        clubs += members
    return clubs


def _draw(conn: Connection, world: World, meta: CareerMeta, calendar: SeasonCalendarDef,
          cup: CupDef, round_index: int, today: date) -> list[str]:
    season_id = meta.season_id
    competition_id = competition_ids(conn, world, calendar)[cup.key]
    rnd = cup.rounds[round_index]
    standing = _standing(conn, world, season_id)
    carried = [t.winner_club_id for t in _ties(conn, season_id, competition_id)
               if t.round == round_index - 1]
    clubs = carried + _entrants(conn, cup, round_index, season_id, standing)
    through = rnd.qualifiers if rnd.qualifiers is not None else len(clubs) // 2
    exempt = sorted(clubs, key=lambda c: standing.get(c, (99, 99, 99, 0)))[:2 * through
                                                                           - len(clubs)]
    playing = [c for c in clubs if c not in set(exempt)]
    rng = derive_rng(meta.seed, "cup-draw", season_id, cup.key, round_index)
    order = [playing[k] for k in rng.permutation(len(playing))]
    ties = list(zip(order[0::2], order[1::2], strict=True))
    rows = [{"tie": f"B{n}", "club_a_id": c, "club_b_id": None, "winner_club_id": c}
            for n, c in enumerate(exempt, start=1)]
    rows += [{"tie": str(n), "club_a_id": a, "club_b_id": b, "winner_club_id": None}
             for n, (a, b) in enumerate(ties, start=1)]
    conn.execute(cup_tie.insert(), [{"season_id": season_id, "competition_id": competition_id,
                                     "round": round_index, **row} for row in rows])
    days = calendar.cups[cup.key][round_index]
    for n, (a, b) in enumerate(ties, start=1):
        legs = [(a, b)] if rnd.legs == 1 else [(a, b), (b, a)]
        for leg, ((home, away), day) in enumerate(zip(legs, days, strict=True), start=1):
            conn.execute(fixture.insert().values(
                season_id=season_id, competition_id=competition_id, stage=cup.key,
                round=round_index, tie=str(n), leg=leg if rnd.legs == 2 else None,
                date=day.isoformat(), home_club_id=home, away_club_id=away,
                neutral=int(rnd.neutral), status="scheduled"))
    for a, b in ties:
        for club_id in (a, b):
            for day in days:
                _clear_way(conn, world, calendar, club_id, day, today)
    return _draw_news(conn, meta, cup, round_index, ties, exempt, days)


def _clear_way(conn: Connection, world: World, calendar: SeasonCalendarDef, club_id: int,
               cup_day: date, today: date) -> None:
    """Move any league match of ``club_id`` too close to his cup match on ``cup_day``."""
    window = ((cup_day - timedelta(days=REST_DAYS)).isoformat(),
              (cup_day + timedelta(days=REST_DAYS)).isoformat())
    clashes = conn.execute(select(fixture).where(
        fixture.c.status == "scheduled", fixture.c.stage == "league",
        or_(fixture.c.home_club_id == club_id, fixture.c.away_club_id == club_id),
        fixture.c.date.between(*window))).all()
    for fx in clashes:
        day = _free_day(conn, world, calendar, fx, today)
        if day is not None:
            conn.execute(update(fixture).where(fixture.c.id == fx.id)
                         .values(date=day.isoformat()))


def _free_day(conn: Connection, world: World, calendar: SeasonCalendarDef, fx: Row[Any],
              today: date) -> date | None:
    """The nearest day both clubs are free for a moved league match (a midweek if possible,
    and later rather than earlier), after today, within the league's season, and clear of the
    season's cup dates."""
    key: str = conn.execute(select(competition.c.key).where(
        competition.c.id == fx.competition_id)).scalar_one()
    dates = calendar.competitions[key]
    clubs = (fx.home_club_id, fx.away_club_id)
    busy: set[date] = set()
    for row in conn.execute(select(fixture.c.date).where(
            fixture.c.id != fx.id,
            or_(fixture.c.home_club_id.in_(clubs), fixture.c.away_club_id.in_(clubs)))):
        played = date.fromisoformat(row.date)
        busy.update(played + timedelta(days=k) for k in range(-REST_DAYS, REST_DAYS + 1))
    cup_days = {day + timedelta(days=k) for rounds in calendar.cups.values() for legs in rounds
                for day in legs for k in range(-REST_DAYS, REST_DAYS + 1)}
    original = date.fromisoformat(fx.date)
    free = []
    day = max(today + timedelta(days=1), dates.start)
    while day <= dates.end:
        paused = dates.pause_for_international_windows and calendar.in_international_window(day)
        if day not in busy and not paused:
            free.append(day)
        day += timedelta(days=1)
    clear = [d for d in free if d not in cup_days] or free
    if not clear:
        return None
    return min(clear, key=lambda d: (d.weekday() not in MIDWEEK, abs((d - original).days),
                                     d < original))


def _draw_news(conn: Connection, meta: CareerMeta, cup: CupDef, round_index: int,
               ties: list[tuple[int, int]], exempt: list[int], days: list[date]) -> list[str]:
    user = meta.user_club_id
    if user is None:
        return []
    name = cup.rounds[round_index].name
    if user in exempt:
        return [f"{club_name(conn, user)} are exempt from the {cup.name} {name.lower()}."]
    for a, b in ties:
        if user in (a, b):
            when = " and ".join(f"{d:%a} {d.day} {d:%b}" for d in days)
            return [f"{cup.name} {name.lower()} draw: {club_name(conn, a)} v "
                    f"{club_name(conn, b)} ({when})."]
    return []


def _results_news(conn: Connection, meta: CareerMeta, cup: CupDef, round_index: int,
                  decided: list[tuple[Row[Any], int]]) -> list[str]:
    user = meta.user_club_id
    if user is None:
        return []
    for tie, winner in decided:
        if user in (tie.club_a_id, tie.club_b_id) and winner != user:
            name = cup.rounds[round_index].name.lower()
            return [f"{club_name(conn, user)} are out of the {cup.name}, beaten by "
                    f"{club_name(conn, winner)} in the {name}."]
    return []
