"""Knockout cups (P17): the FA Cup and the Carabao Cup's formats add up, and leagues are
scheduled around the cup rounds that keep them out."""

from footsim.competitions.scheduling import league_round_dates
from footsim.defs.loader import load_definitions
from footsim.world.context import get_world
from footsim.world.cups import blocked_dates


def test_the_cups_add_up() -> None:
    defs = load_definitions()
    sizes = {key: league.clubs for key, league in defs.leagues.items()}
    # The FA Cup: League One and Two's 48 (the best exempt for the missing non-league
    # qualifiers), then 64 in the third round with the Premier League and Championship.
    assert defs.cups["FA_CUP"].sizes(sizes) == [
        (48, 32), (32, 20), (64, 32), (32, 16), (16, 8), (8, 4), (4, 2), (2, 1)]
    # The Carabao Cup: the EFL's 72, then twelve Premier League clubs, then the top eight.
    assert defs.cups["EFL_CUP"].sizes(sizes) == [
        (72, 36), (48, 24), (32, 16), (16, 8), (8, 4), (4, 2), (2, 1)]
    calendar = defs.calendars["ENG-2026-27"]
    assert [len(legs) for legs in calendar.cups["EFL_CUP"]] == [1, 1, 1, 1, 1, 2, 1]


def test_leagues_keep_clear_of_the_cup_rounds_that_block_them() -> None:
    world = get_world()
    calendar = world.defs.calendars["ENG-2026-27"]
    for key, rounds in (("ENG1", 38), ("ENG2", 46), ("ENG3", 46), ("ENG4", 46)):
        blocked = blocked_dates(world, calendar, key)
        days = league_round_dates(calendar.competitions[key], calendar, rounds, blocked)
        assert len(days) == rounds and not set(days) & blocked
        assert all((b - a).days >= 3 for a, b in zip(days, days[1:], strict=False))
    assert len(blocked_dates(world, calendar, "ENG1")) == 6  # FA Cup third round to the final
    assert len(blocked_dates(world, calendar, "ENG3")) == 1  # its first round
