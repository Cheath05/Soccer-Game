"""The European competitions' definitions (defs/europe.py, data/config/europe/): formats, UEFA's
access list by ranking position, dates and prizes check out, and a broken access list is an
error. (That the access list's rounds add up to 36-club league phases: test_europe_qualifying_
plan.py.)"""

import pytest
from pydantic import ValidationError

from footsim.defs.europe import AccessListFile, AccessPlaceDef, LeaguePhaseDef, check_europe
from footsim.world.context import get_world


def test_the_three_competitions_load() -> None:
    defs = get_world().defs
    assert [c.key for c in sorted(defs.continental.values(), key=lambda c: c.rank)] == [
        "UCL", "UEL", "UECL"]
    ucl = defs.continental["UCL"].league_phase
    assert (ucl.clubs, ucl.matches, ucl.per_pot, ucl.pot_size) == (36, 8, 2, 9)
    uecl = defs.continental["UECL"].league_phase
    assert (uecl.matches, uecl.per_pot, uecl.pot_size) == (6, 1, 6)
    assert [r.key for r in defs.continental["UCL"].qualifying] == ["Q1", "Q2", "Q3", "PO"]
    nodes = {(n.round, n.path): n for n in defs.europe_access.competitions["UCL"].nodes}
    first = nodes[("Q1", "champions")].losers
    assert first is not None and (first.competition, first.round, first.path) == (
        "UECL", "Q2", "champions")
    holders = [p.holder for p in defs.europe_access.competitions["UCL"].places if p.holder]
    assert holders == ["UCL", "UEL"]


def _errors(raw: dict) -> list[str]:  # type: ignore[type-arg]
    defs = get_world().defs
    return check_europe(defs.continental, AccessListFile.model_validate(raw),
                        defs.europe_calendars, defs.europe, defs.finance.europe_prizes,
                        set(defs.nations), {c.key: c.nation for c in defs.cups.values()})


def test_a_broken_access_list_is_an_error() -> None:
    defs = get_world().defs
    assert _errors(defs.europe_access.model_dump()) == []
    raw = defs.europe_access.model_dump()
    raw["competitions"]["UEL"]["nodes"][0]["losers"]["path"] = "champions"
    raw["competitions"]["UEL"]["nodes"][0]["losers"]["round"] = "Q1"  # UECL Q1 has no such path
    raw["cups"]["ENG"] = "COPA_DEL_REY"
    errors = _errors(raw)
    assert any("no round Q1 champions in UECL" in e for e in errors)
    assert any("COPA_DEL_REY isn't a cup of ENG" in e for e in errors)


def test_places_and_formats_are_checked() -> None:
    with pytest.raises(ValidationError, match="a place is"):
        AccessPlaceDef(round="LP", ranks=(1, 4), positions=(1, 1), holder="UCL")
    with pytest.raises(ValidationError, match="positions or the cup"):
        AccessPlaceDef(round="LP", ranks=(1, 4))
    with pytest.raises(ValidationError, match="has a path"):
        AccessPlaceDef(round="Q1", ranks=(20, 30), cup=True)
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
    for key in ("UCL", "UEL", "UECL"):
        assert list(dates[key].qualifying) == ["Q1", "Q2", "Q3", "PO"]
        assert all(len(legs) == 2 for legs in dates[key].qualifying.values())
    assert all(day.weekday() in (1, 2) for legs in dates["UCL"].qualifying.values()
               for leg in legs for day in leg)
