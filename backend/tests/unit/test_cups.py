"""Knockout cups (P17): each country's cups have formats that add up, are dated on their own
country's calendar, and leagues are scheduled around the cup rounds that keep them out."""

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import insert

from footsim.competitions.calendars import shifted_calendar
from footsim.competitions.scheduling import league_round_dates, playoff_dates
from footsim.defs.calendar import SeasonCalendarDef
from footsim.defs.loader import load_definitions
from footsim.persistence.database import open_database
from footsim.persistence.schema import competition, metadata
from footsim.world.context import get_world
from footsim.world.cups import blocked_dates, cups_in_play, season_cups

# England's two cups share days with league rounds (the Championship and the lower leagues are
# not kept out of most of their rounds); the season moves those league matches around the ties.
# Every cup after them is dated clear of its country's league rounds, which the tests below hold.
REARRANGED = {"FA_CUP", "EFL_CUP"}


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


def test_each_countrys_cups_add_up() -> None:
    defs = load_definitions()
    sizes = {key: league.clubs for key, league in defs.leagues.items()}
    last = [(8, 4), (4, 2), (2, 1)]
    # Where a league's clubs don't make a bracket, the top-ranked are exempt (byes) in the first
    # round so the next has 16 (or 32); each cup's entrants and rounds are explained in its file.
    assert defs.cups["COPA_DEL_REY"].sizes(sizes) == [(38, 28), (32, 16), (16, 8), *last]
    assert defs.cups["COPPA_ITALIA"].sizes(sizes) == [(32, 16), (16, 8), (16, 8), *last]
    assert defs.cups["DFB_POKAL"].sizes(sizes) == [(56, 32), (32, 16), (16, 8), *last]
    assert defs.cups["COUPE_DE_FRANCE"].sizes(sizes) == [(18, 14), (32, 16), (16, 8), *last]
    assert defs.cups["TACA_DA_LIGA"].sizes(sizes) == last
    assert defs.cups["SCOTTISH_CUP"].sizes(sizes) == [(12, 8), *last]
    assert defs.cups["SCOTTISH_LEAGUE_CUP"].sizes(sizes) == [(12, 8), *last]
    for key in ("TACA_DE_PORTUGAL", "KNVB_BEKER", "TURKISH_CUP", "BELGIAN_CUP", "KINGS_CUP"):
        assert defs.cups[key].sizes(sizes) == [(18, 16), (16, 8), *last], key
    # Two-legged semi-finals where the real cup has them, and neutral finals everywhere.
    legs = {key: [r.legs for r in cup.rounds] for key, cup in defs.cups.items()}
    two_legged = {"EFL_CUP", "COPA_DEL_REY", "COPPA_ITALIA", "TACA_DE_PORTUGAL", "BELGIAN_CUP"}
    assert {key for key, rounds in legs.items() if 2 in rounds} == two_legged
    assert all(cup.rounds[-1].neutral for cup in defs.cups.values())


def test_every_cup_is_dated_on_its_own_countrys_calendar() -> None:
    defs = load_definitions()
    for key, cup in defs.cups.items():
        dated = [c for c in defs.calendars.values() if key in c.cups]
        assert [c.nation for c in dated] == [cup.nation], key
        assert {defs.leagues[e.league].nation for e in cup.entrants} == {cup.nation}, key
    # Every country in the game has a cup.
    assert {c.nation for c in defs.cups.values()} == {lg.nation for lg in defs.leagues.values()}


def _cup_days(calendar: SeasonCalendarDef, key: str) -> list[date]:
    return [day for legs in calendar.cups[key] for day in legs]


@pytest.mark.parametrize("years", range(4))
def test_cups_keep_clear_of_their_countrys_league_days(years: int) -> None:
    """In this season and the next three (calendars move forward a year at a time): a cup's
    rounds fall outside its country's international windows and winter break, three or more days
    from its other cups' and from every round of its leagues (play-offs included), and leagues
    still fit their rounds in with the days the cup rounds that block them keep free."""
    world = get_world()
    for base in world.defs.calendars.values():
        calendar = shifted_calendar(base, years)
        every = sorted((day, key) for key in calendar.cups for day in _cup_days(calendar, key))
        for (a, key_a), (b, key_b) in zip(every, every[1:], strict=False):
            assert (b - a).days >= 3, (key_a, a, key_b, b)
        league_days: list[date] = []
        for key, league in world.defs.leagues.items():
            if league.calendar != base.key:
                continue
            dates = calendar.competitions[key]
            blocked = blocked_dates(world, calendar, key)
            days = league_round_dates(dates, calendar, league.format.legs * (league.clubs - 1),
                                      blocked)
            assert not set(days) & blocked, key
            league_days += days
            for playoff in league.playoffs:
                league_days += [day for legs in playoff_dates(dates.end, dates.playoffs_end,
                                                              playoff.rounds) for day in legs]
        for day, key in every:
            if key in REARRANGED:
                continue
            assert not any(b.contains(day) for b in calendar.blackout), (key, day)
            assert not calendar.in_international_window(day), (key, day)
            assert min(abs((day - league).days) for league in league_days) >= 3, (key, day)


def test_the_leagues_a_cup_round_blocks_play_nothing_that_day() -> None:
    world = get_world()
    scotland = world.defs.calendars["SCO-2026-27"]
    blocked = blocked_dates(world, scotland, "SCO1")
    # The Scottish Cup semi-finals, and the League Cup semi-finals and final: all Saturdays.
    assert blocked == {date(2027, 4, 17), date(2026, 10, 31), date(2026, 12, 12)}
    assert blocked_dates(world, world.defs.calendars["ESP-2026-27"], "ESP1") == set()


def test_every_calendars_cups_are_found_for_a_season() -> None:
    world = get_world()
    found = {cup.key: calendar for cup, calendar in season_cups(world, 2)}
    assert set(found) == set(world.defs.cups)
    assert all(calendar.nation == world.defs.cups[key].nation for key, calendar in found.items())
    assert all(calendar.season == "2027-28" for calendar in found.values())


def test_a_cup_is_only_played_where_the_career_has_its_leagues(tmp_path: Path) -> None:
    """A save from before a country's league has none of its cups until the league is added."""
    world = get_world()
    engine = open_database(tmp_path / "save.sqlite")
    metadata.create_all(engine)
    with engine.begin() as conn:
        for key in ("ENG1", "ENG2", "ENG3", "ENG4", "ESP1"):
            conn.execute(insert(competition).values(
                key=key, name=key, short_name=key, type="league", tier=1, sim_level="simulated"))
        assert {c.key for c, _ in cups_in_play(conn, world, 1)} == {"FA_CUP", "EFL_CUP"}
        conn.execute(insert(competition).values(
            key="ESP2", name="ESP2", short_name="ESP2", type="league", tier=2,
            sim_level="simulated"))
        assert {c.key for c, _ in cups_in_play(conn, world, 1)} == {
            "FA_CUP", "EFL_CUP", "COPA_DEL_REY"}
    engine.dispose()
