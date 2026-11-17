"""The game's world with MLS as league USA1, for the roster-rule tests (W9a B3-B4): the league of
test_league_formats.py (conferences, play-offs), its calendar with MLS's transfer windows, and
its league income. The Americas' own data files come from another checkpoint (B2); the tests
define the league here so they check the rules, not those files."""

from dataclasses import replace
from typing import Any

from test_league_formats import WINDOWS, _mls

from footsim.defs.calendar import SeasonCalendarDef
from footsim.defs.competitions import LeagueDef
from footsim.defs.finance import LeagueIncome
from footsim.world.context import World, get_world


def _calendar() -> SeasonCalendarDef:
    raw: dict[str, Any] = {
        "key": "TST-MLS", "season": "2026-27", "nation": "USA", "season_start": "2026-07-01",
        "season_end": "2027-06-30",
        "competitions": {"USA1": {"start": "2026-07-18", "end": "2027-04-25",
                                  "playoffs_end": "2027-05-29"}},
        "international_windows": WINDOWS,
        "blackout": [{"start": "2026-12-14", "end": "2027-02-05"}],
        # MLS's primary window in the summer, its secondary in the winter.
        "transfer_windows": [{"start": "2026-07-01", "end": "2026-09-01"},
                             {"start": "2027-01-15", "end": "2027-03-10"}]}
    return SeasonCalendarDef.model_validate(raw)


def mls_world() -> World:
    base = get_world()
    league = LeagueDef.model_validate({**_mls(), "calendar": "TST-MLS"})
    income = {**base.defs.finance.league_income,
              "USA1": LeagueIncome(base=8_000_000, merit=4_000_000)}
    defs = replace(base.defs, leagues={**base.defs.leagues, "USA1": league},
                   calendars={**base.defs.calendars, "TST-MLS": _calendar()},
                   finance=base.defs.finance.model_copy(update={"league_income": income}))
    return World(defs=defs, model=base.model, picker=base.picker, quick=base.quick,
                 fast=base.fast)
