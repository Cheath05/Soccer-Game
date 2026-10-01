"""Turns rounds into calendar dates.

League rounds go on Saturdays between the competition's start and end dates, skipping
international windows when the league pauses for them. If there aren't enough weekends,
evenly spread Tuesday rounds are added between two consecutive weekend rounds, so every
club always gets at least two full rest days between matches.
"""

from datetime import date, timedelta

import numpy as np

from footsim.defs.calendar import CompetitionDates, SeasonCalendarDef
from footsim.defs.competitions import PlayoffRoundDef

SATURDAY = 5
MIDWEEK_OFFSET = 3  # Saturday -> Tuesday
PLAYOFF_GAP = 4  # days between play-off matches


class SchedulingError(Exception):
    pass


def _spread(items: list[date], count: int) -> list[date]:
    """``count`` items spread evenly across ``items`` (keeps the first and last)."""
    if count <= 0:
        return []
    if count >= len(items):
        return list(items)
    picks = np.linspace(0, len(items) - 1, count).round().astype(int)
    return [items[i] for i in picks]


def league_round_dates(
    dates: CompetitionDates, calendar: SeasonCalendarDef, rounds: int,
    reserved: frozenset[date] | set[date] = frozenset(),
) -> list[date]:
    """``reserved``: days the league plays nothing (a cup round's, say)."""

    def blocked(day: date) -> bool:
        return day in reserved or (dates.pause_for_international_windows
                                   and calendar.in_international_window(day))

    first = dates.start + timedelta(days=(SATURDAY - dates.start.weekday()) % 7)
    weekends = []
    day = first
    while day <= dates.end:
        if not blocked(day) and not any(b.contains(day) for b in calendar.blackout):
            weekends.append(day)
        day += timedelta(days=7)

    if len(weekends) >= rounds:
        return _spread(weekends, rounds)

    midweeks = [
        sat + timedelta(days=MIDWEEK_OFFSET)
        for sat, nxt in zip(weekends, weekends[1:], strict=False)
        if (nxt - sat).days == 7 and not blocked(sat + timedelta(days=MIDWEEK_OFFSET))
    ]
    needed = rounds - len(weekends)
    if len(midweeks) < needed:
        raise SchedulingError(
            f"{rounds} rounds don't fit between {dates.start} and {dates.end}: "
            f"{len(weekends)} weekends and {len(midweeks)} usable midweeks"
        )
    return sorted(weekends + _spread(midweeks, needed))


def playoff_dates(
    league_end: date, playoffs_end: date | None, rounds: list[PlayoffRoundDef]
) -> list[list[date]]:
    """Dates for each leg of each play-off round, starting a few days after the league."""
    result: list[list[date]] = []
    day = league_end + timedelta(days=PLAYOFF_GAP)
    for index, rnd in enumerate(rounds):
        if index == len(rounds) - 1 and playoffs_end is not None:
            day = max(day, playoffs_end - timedelta(days=PLAYOFF_GAP * (rnd.legs - 1)))
        legs = [day + timedelta(days=PLAYOFF_GAP * leg) for leg in range(rnd.legs)]
        result.append(legs)
        day = legs[-1] + timedelta(days=PLAYOFF_GAP)
    return result
