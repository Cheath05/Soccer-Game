"""Transfer windows (W4-2; docs/plans/w3-w4-finances-transfers.md).

Each country's calendar sets its summer and winter windows. A move is allowed when the buying
club's country has a window open: the country of the league it plays in, or for a club outside
the game's leagues its own country (``market.default_window_nation`` when the game has no
calendar for it). The summer window can open before the season does (England's opens in mid
June, before the 1 July rollover), so a day is checked against both the current season's
calendar and the next one's.
"""

from datetime import date

from sqlalchemy import Connection, text

from footsim.competitions.calendars import shifted_calendar
from footsim.defs.calendar import DateRange, SeasonCalendarDef
from footsim.world.context import World


def _base_calendar(world: World, nation: str) -> SeasonCalendarDef:
    """The country's own calendar (as built, for the first season), or the default country's."""
    by_nation = {c.nation: c for c in sorted(world.defs.calendars.values(), key=lambda c: c.key)}
    return by_nation.get(nation) or by_nation[world.defs.market.default_window_nation]


def open_window(world: World, nation: str, season_id: int, day: date) -> DateRange | None:
    """The window open for ``nation`` on ``day`` in season ``season_id``, if any."""
    base = _base_calendar(world, nation)
    for season in (season_id, season_id + 1):
        calendar = shifted_calendar(base, season - 1)
        for window in calendar.transfer_windows:
            if window.contains(day):
                return window
    return None


def window_open(world: World, nation: str, season_id: int, day: date) -> bool:
    return open_window(world, nation, season_id, day) is not None


def club_window_nation(conn: Connection, club_id: int, season_id: int) -> str:
    """Whose windows a club follows: the country of the league it plays in this season, else its
    own country's."""
    row = conn.execute(text(
        "SELECT (SELECT n.code FROM club_league_membership m JOIN competition c "
        "        ON c.id = m.competition_id JOIN nation n ON n.id = c.nation_id "
        "        WHERE m.club_id = :club AND m.season_id = :season) AS league_nation, "
        "       (SELECT n.code FROM club k JOIN nation n ON n.id = k.nation_id "
        "        WHERE k.id = :club) AS own_nation"), {"club": club_id, "season": season_id}).one()
    return str(row.league_nation or row.own_nation or "")
