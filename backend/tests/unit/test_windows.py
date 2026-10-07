"""Transfer windows (W4-2): each country's own, across the season's turn."""

from datetime import date

import pytest

from footsim.world.context import get_world
from footsim.world.windows import open_window, window_open

DAYS = {
    # England's summer window opens in mid June, before the 1 July rollover.
    ("ENG", 1, date(2026, 8, 15)): True,
    ("ENG", 1, date(2026, 10, 1)): False,
    ("ENG", 1, date(2027, 1, 15)): True,
    ("ENG", 1, date(2027, 3, 1)): False,
    ("ENG", 1, date(2027, 6, 10)): False,
    ("ENG", 1, date(2027, 6, 20)): True,  # next season's window, still this season
    ("ENG", 2, date(2027, 8, 20)): True,
    ("ENG", 3, date(2029, 1, 20)): True,  # windows move on with the seasons
    # Spain's opens on 1 July: the same June day is closed there.
    ("ESP", 1, date(2027, 6, 20)): False,
    ("ESP", 2, date(2027, 7, 1)): True,
    ("TUR", 1, date(2027, 2, 5)): True,  # Turkey's winter window runs later
    ("GER", 1, date(2027, 2, 5)): False,
}


@pytest.mark.parametrize(("nation", "season", "day"), list(DAYS))
def test_a_window_is_open_on_its_countrys_days(nation: str, season: int, day: date) -> None:
    assert window_open(get_world(), nation, season, day) is DAYS[(nation, season, day)]


def test_a_country_without_a_calendar_follows_the_default() -> None:
    world = get_world()
    default = world.defs.market.default_window_nation
    for day in (date(2026, 8, 15), date(2026, 10, 1), date(2027, 1, 15)):
        assert window_open(world, "BRA", 1, day) is window_open(world, default, 1, day)


def test_the_open_window_says_when_it_closes() -> None:
    window = open_window(get_world(), "ENG", 1, date(2026, 8, 15))
    assert window is not None and window.end == date(2026, 9, 1)
