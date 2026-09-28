"""Calendars for seasons after the ones defined in data.

A later season reuses the latest defined calendar, moved forward by whole years and nudged
to the same weekday (a Saturday round stays a Saturday). Dates therefore don't drift.
"""

from datetime import date, timedelta

from footsim.defs.calendar import CompetitionDates, DateRange, SeasonCalendarDef


def shift_keep_weekday(day: date, years: int) -> date:
    try:
        target = day.replace(year=day.year + years)
    except ValueError:  # 29 February
        target = day.replace(year=day.year + years, day=28)
    offset = (day.weekday() - target.weekday()) % 7
    if offset > 3:
        offset -= 7
    return target + timedelta(days=offset)


def season_label(start_year: int) -> str:
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def shifted_calendar(base: SeasonCalendarDef, years: int) -> SeasonCalendarDef:
    if years == 0:
        return base

    def s(day: date) -> date:
        return shift_keep_weekday(day, years)

    def r(rng: DateRange) -> DateRange:
        return DateRange(start=s(rng.start), end=s(rng.end))

    start_year = base.season_start.year + years
    label = season_label(start_year)
    return SeasonCalendarDef(
        key=f"{base.nation}-{label}",
        season=label,
        nation=base.nation,
        season_start=base.season_start.replace(year=start_year),
        season_end=base.season_end.replace(year=start_year + 1),
        competitions={
            key: CompetitionDates(
                start=s(c.start),
                end=s(c.end),
                playoffs_end=s(c.playoffs_end) if c.playoffs_end else None,
                pause_for_international_windows=c.pause_for_international_windows,
            )
            for key, c in base.competitions.items()
        },
        international_windows=[r(w) for w in base.international_windows],
        transfer_windows=[r(w) for w in base.transfer_windows],
        blackout=[r(b) for b in base.blackout],
    )
