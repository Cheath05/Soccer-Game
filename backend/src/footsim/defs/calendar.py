"""Season calendars per association (data/config/calendars/*.yaml)."""

from datetime import date

from pydantic import model_validator

from footsim.defs.common import DefModel


class DateRange(DefModel):
    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> "DateRange":
        if self.end < self.start:
            raise ValueError(f"range ends before it starts: {self.start} > {self.end}")
        return self

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end


class CompetitionDates(DefModel):
    start: date
    end: date
    playoffs_end: date | None = None
    pause_for_international_windows: bool = True

    @model_validator(mode="after")
    def _ordered(self) -> "CompetitionDates":
        if self.end < self.start:
            raise ValueError("competition ends before it starts")
        if self.playoffs_end is not None and self.playoffs_end < self.end:
            raise ValueError("play-offs cannot finish before the regular season")
        return self


class SeasonCalendarDef(DefModel):
    key: str
    season: str
    nation: str
    season_start: date
    season_end: date
    competitions: dict[str, CompetitionDates]
    international_windows: list[DateRange] = []
    transfer_windows: list[DateRange] = []
    blackout: list[DateRange] = []

    @model_validator(mode="after")
    def _within_season(self) -> "SeasonCalendarDef":
        season = DateRange(start=self.season_start, end=self.season_end)
        for key, comp in self.competitions.items():
            last = comp.playoffs_end or comp.end
            if not (season.contains(comp.start) and season.contains(last)):
                raise ValueError(f"{self.key}: {key} dates fall outside the season")
        return self

    def in_international_window(self, day: date) -> bool:
        return any(w.contains(day) for w in self.international_windows)
