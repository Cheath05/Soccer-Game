"""The calendar view: the user's fixtures in a date range, the days their club's transfer
window is open, the season's bounds and the international breaks."""

from datetime import date, timedelta

from pydantic import BaseModel
from sqlalchemy import Connection

from footsim.api import queries
from footsim.api.schemas import FixtureOut
from footsim.world.context import World
from footsim.world.meta import read_meta
from footsim.world.season import season_calendar
from footsim.world.windows import club_window_nation, window_open

MAX_RANGE_DAYS = 400


class DateSpan(BaseModel):
    start: str
    end: str


class CalendarOut(BaseModel):
    start: str
    end: str
    today: str
    season_start: str
    season_end: str
    fixtures: list[FixtureOut]
    window_days: list[str]  # days in range on which the user's club's transfer window is open
    international_breaks: list[DateSpan]


def calendar(conn: Connection, world: World, start: date, end: date) -> CalendarOut:
    meta = read_meta(conn)
    assert meta.user_club_id is not None
    sid = meta.season_id
    nation = club_window_nation(conn, meta.user_club_id, sid)
    window_days: list[str] = []
    day = start
    while day <= end:
        if any(window_open(world, nation, s, day) for s in {max(1, sid - 1), sid}):
            window_days.append(day.isoformat())
        day += timedelta(days=1)
    breaks: set[tuple[date, date]] = set()
    for s in range(max(1, sid - 1), sid + 2):
        for w in season_calendar(world, meta, s).international_windows:
            if w.end >= start and w.start <= end:
                breaks.add((w.start, w.end))
    current = season_calendar(world, meta, sid)
    fixtures = [f for f in queries.fixtures(conn, club_id=meta.user_club_id, season_id=None)
                if start.isoformat() <= f.date <= end.isoformat()]
    if start < current.season_start:  # earlier seasons' fixtures too
        for s in range(max(1, sid - 1), sid):
            fixtures += [f for f in queries.fixtures(conn, club_id=meta.user_club_id, season_id=s)
                         if start.isoformat() <= f.date <= end.isoformat()]
    if end > current.season_end:
        fixtures += [f for f in queries.fixtures(conn, club_id=meta.user_club_id, season_id=sid + 1)
                     if start.isoformat() <= f.date <= end.isoformat()]
    fixtures.sort(key=lambda f: (f.date, f.id))
    return CalendarOut(
        start=start.isoformat(), end=end.isoformat(), today=meta.current_date.isoformat(),
        season_start=current.season_start.isoformat(), season_end=current.season_end.isoformat(),
        fixtures=fixtures, window_days=window_days,
        international_breaks=[DateSpan(start=a.isoformat(), end=b.isoformat())
                              for a, b in sorted(breaks)])
