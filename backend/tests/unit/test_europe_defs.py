"""The European competitions' definitions (defs/europe.py, data/config/europe/): formats,
access, dates and prizes add up, and every country without a league in the game has the clubs
its places need."""

import sqlite3
from collections import Counter

import pytest
from pydantic import ValidationError

from footsim.core.paths import data_dir
from footsim.defs.europe import AccessFile, LeaguePhaseDef, PlaceDef, check_europe
from footsim.world.context import get_world

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"


def test_the_three_competitions_load() -> None:
    defs = get_world().defs
    assert [c.key for c in sorted(defs.continental.values(), key=lambda c: c.rank)] == [
        "UCL", "UEL", "UECL"]
    ucl = defs.continental["UCL"].league_phase
    assert (ucl.clubs, ucl.matches, ucl.per_pot, ucl.pot_size) == (36, 8, 2, 9)
    uecl = defs.continental["UECL"].league_phase
    assert (uecl.matches, uecl.per_pot, uecl.pot_size) == (6, 1, 6)
    assert defs.continental["UCL"].qualifying.losers_to == "UEL"
    assert defs.continental["UEL"].winner_to == "UCL"


def test_every_league_phase_comes_to_36() -> None:
    defs = get_world().defs
    access = defs.europe_access.competitions
    assert (access["UCL"].direct(), access["UCL"].qualifiers()) == (32, 8)
    # The Europa League: 26 direct, 6 through its play-off, 4 dropping from the UCL's.
    assert access["UEL"].direct() + 6 + 4 == 36
    assert access["UECL"].direct() + access["UECL"].qualifiers() // 2 + 6 == 36


def test_a_miscounted_access_list_is_an_error() -> None:
    defs = get_world().defs
    raw = defs.europe_access.model_dump()
    raw["competitions"]["UCL"]["league_phase"].pop()  # one place short
    errors = check_europe(
        defs.continental, AccessFile.model_validate(raw), defs.europe_calendars, defs.europe,
        defs.finance.europe_prizes, set(defs.nations),
        {lg.nation for lg in defs.leagues.values() if lg.tier == 1},
        {c.key: c.nation for c in defs.cups.values()})
    assert any("UCL: the access list makes 35" in e for e in errors)


def test_places_and_formats_are_checked() -> None:
    with pytest.raises(ValidationError, match="a place is"):
        PlaceDef(nation="ENG", ranks=(1, 4), cup="FA_CUP")
    with pytest.raises(ValidationError, match="divide into the pots"):
        LeaguePhaseDef(clubs=36, matches=8, pots=5, to_round_of_16=8, to_playoff=(9, 24))
    with pytest.raises(ValidationError, match="even number of pots"):
        LeaguePhaseDef(clubs=35, matches=5, pots=5, to_round_of_16=8, to_playoff=(9, 24))


def test_the_calendar_has_every_stage() -> None:
    defs = get_world().defs
    dates = defs.europe_calendars[defs.europe.calendar].competitions
    assert len(dates["UCL"].league_phase) == 8 and len(dates["UECL"].league_phase) == 6
    assert all(day.weekday() in (1, 2) for md in dates["UCL"].league_phase for day in md)
    assert all(day.weekday() == 3 for md in dates["UEL"].league_phase for day in md)
    assert dates["UCL"].knockout[-1][0][0].weekday() == 5  # the final, a Saturday


@pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
def test_countries_without_a_league_have_the_clubs_their_places_need() -> None:
    defs = get_world().defs
    with_league = {lg.nation for lg in defs.leagues.values() if lg.tier == 1}
    needed: Counter[str] = Counter()
    for rules in defs.europe_access.competitions.values():
        for place in [*rules.league_phase, *rules.qualifying]:
            if place.nation and place.ranks and place.nation not in with_league:
                needed[place.nation] = max(needed[place.nation], place.ranks[1])
    with sqlite3.connect(f"file:{BASE_WORLD}?mode=ro", uri=True) as conn:
        clubs = dict(conn.execute(
            "SELECT n.code, count(*) FROM club c JOIN nation n ON n.id = c.nation_id "
            "GROUP BY n.code").fetchall())
    short = {nation: (rank, clubs.get(nation, 0)) for nation, rank in needed.items()
             if clubs.get(nation, 0) < rank}
    assert not short, f"countries without enough clubs for their places: {short}"
