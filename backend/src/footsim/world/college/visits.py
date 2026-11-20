"""Game-day visits (20 Nov): a college coach invites a recruit to one of their home games for his
official visit, and the result sways him.

The visit is one of the program's official visits (``programs.official_visits``), at most
``gameday_visit.per_game`` recruits a game, before signing day. Once the game is played the
recruit's interest in the program rises by the visit's boost (``programs.visit_boost``) times the
result's factor: a win more than a draw, a big win most, a loss much less. A recruit invited to a
game isn't also given the automatic visit of a keen Top target (recruiting.py ``_effort``). The
career's meta keeps the invitations until their games are played."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Connection, Row, select, text

from footsim.persistence.schema import club, fixture, recruit
from footsim.world.college import recruiting as rc
from footsim.world.college.common import is_college_club
from footsim.world.context import World
from footsim.world.meta import CareerMeta, write_meta


class VisitRefused(ValueError):
    """Why that visit can't be arranged, for the user."""


@dataclass(frozen=True)
class HomeGame:
    fixture_id: int
    date: date
    opponent: str
    invited: list[int]  # recruit ids


def visits_used(conn: Connection, meta: CareerMeta, club_id: int) -> int:
    done = int(conn.execute(text(
        "SELECT COUNT(*) FROM recruit_interest i JOIN recruit r ON r.id = i.recruit_id "
        "WHERE r.class_season = :c AND i.club_id = :club AND i.visited_on IS NOT NULL"),
        {"c": meta.season_id + 1, "club": club_id}).scalar_one())
    return done + len(meta.gameday_visits)


def home_games(conn: Connection, world: World, meta: CareerMeta) -> list[HomeGame]:
    """The user's home games a recruit can still visit: from today to signing day."""
    user = meta.user_club_id
    if user is None or not is_college_club(conn, user):
        return []
    dates = rc.recruiting_dates(world.defs.college.recruiting,
                                rc.season_start(conn, meta.season_id))
    names = {int(r.id): str(r.name) for r in conn.execute(select(club.c.id, club.c.name))}
    rows = conn.execute(select(fixture).where(
        fixture.c.home_club_id == user, fixture.c.status == "scheduled",
        fixture.c.neutral == 0, fixture.c.date >= meta.current_date.isoformat(),
        fixture.c.date < dates.signing_day.isoformat()).order_by(fixture.c.date)).all()
    return [HomeGame(int(r.id), date.fromisoformat(r.date), names[int(r.away_club_id)],
                     sorted(rid for rid, fid in meta.gameday_visits.items() if fid == r.id))
            for r in rows]


def invite(conn: Connection, world: World, meta: CareerMeta, recruit_id: int,
           fixture_id: int | None) -> None:
    """Invite a recruit to a home game for his official visit (None: call it off)."""
    from footsim.world.college import coach

    if fixture_id is None:
        meta.gameday_visits.pop(recruit_id, None)
        write_meta(conn, meta)
        return
    user = meta.user_club_id
    if user is None or not is_college_club(conn, user):
        raise VisitRefused("Visits are for a college coach.")
    r = conn.execute(select(recruit).where(recruit.c.id == recruit_id,
                                           recruit.c.class_season == meta.season_id + 1)).first()
    if r is None:
        raise VisitRefused("No such recruit in this year's class.")
    if r.status != rc.OPEN:
        raise VisitRefused("He has already made his choice.")
    game = next((g for g in home_games(conn, world, meta) if g.fixture_id == fixture_id), None)
    if game is None:
        raise VisitRefused("Pick one of your home games before signing day.")
    rules = world.defs.college.recruiting.programs
    visited = conn.execute(text(
        "SELECT visited_on FROM recruit_interest WHERE recruit_id = :r AND club_id = :c"),
        {"r": recruit_id, "c": user}).scalar()
    if visited is not None:
        raise VisitRefused("He has already made his official visit to you.")
    others = [rid for rid in game.invited if rid != recruit_id]
    if len(others) >= rules.gameday_visit.per_game:
        raise VisitRefused(f"That game already has {rules.gameday_visit.per_game} recruits "
                           "visiting.")
    already = recruit_id in meta.gameday_visits
    if not already and visits_used(conn, meta, user) >= rules.official_visits:
        raise VisitRefused(f"You've used all {rules.official_visits} official visits.")
    if conn.execute(text("SELECT priority FROM recruit_interest WHERE recruit_id = :r AND "
                         "club_id = :c"), {"r": recruit_id, "c": user}).scalar() is None:
        coach.set_target(conn, world, meta, recruit_id, rc.WATCH)
    meta.gameday_visits[recruit_id] = fixture_id
    write_meta(conn, meta)


def factor(world: World, scored: int, conceded: int) -> float:
    rules = world.defs.college.recruiting.programs.gameday_visit
    if scored > conceded:
        return rules.big_win if scored - conceded >= rules.big_win_margin else rules.win
    return rules.draw if scored == conceded else rules.loss


def _outcome(fx: Row[Any], user: int) -> tuple[int, int]:
    home = fx.home_club_id == user
    return ((int(fx.home_goals), int(fx.away_goals)) if home
            else (int(fx.away_goals), int(fx.home_goals)))


def settle(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """The visits whose games have been played: each recruit's interest moves with the result.
    Invitations that can't happen any more (he chose, or the game is gone) are dropped."""
    user = meta.user_club_id
    if not meta.gameday_visits or user is None:
        return []
    rules = world.defs.college.recruiting.programs
    names = {int(r.id): str(r.name) for r in conn.execute(select(club.c.id, club.c.name))}
    news: list[str] = []
    changed = False
    for rid, fid in sorted(meta.gameday_visits.items()):
        fx = conn.execute(select(fixture).where(fixture.c.id == fid)).first()
        r = conn.execute(select(recruit).where(recruit.c.id == rid)).first()
        if fx is None or r is None or r.status != rc.OPEN:
            del meta.gameday_visits[rid]
            changed = True
            continue
        if fx.status != "played" or fx.home_goals is None:
            continue
        scored, conceded = _outcome(fx, user)
        row = conn.execute(text("SELECT interest FROM recruit_interest WHERE recruit_id = :r "
                                "AND club_id = :c"), {"r": rid, "c": user}).first()
        before = float(row.interest) if row is not None else 0.0
        after = min(100.0, before + rules.visit_boost * factor(world, scored, conceded))
        conn.execute(text("UPDATE recruit_interest SET interest = :i, visited_on = :d "
                          "WHERE recruit_id = :r AND club_id = :c"),
                     {"i": after, "d": fx.date, "r": rid, "c": user})
        verb = "win" if scored > conceded else "draw" if scored == conceded else "defeat"
        name = " ".join(x for x in (r.first_name, r.last_name) if x)
        news.append(f"{name} watched your {scored}-{conceded} {verb} against "
                    f"{names[int(fx.away_club_id)]} on his visit: his interest in you is now "
                    f"{round(after)} (+{round(after - before)}).")
        del meta.gameday_visits[rid]
        changed = True
    if changed:
        write_meta(conn, meta)
    return news
