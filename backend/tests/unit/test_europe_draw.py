"""W6 E3: the league phase's draw pattern and the placing of clubs (world/europe/league_phase.py),
checked on many seeds: everyone plays once a matchday, the right number from each pot, home and
away as UEFA's rules, never the same club twice, never a club of the same country."""

from collections import Counter, defaultdict

import numpy as np
import pytest

from footsim.world.context import get_world
from footsim.world.europe.league_phase import (
    Pos,
    _block_matchdays,
    _block_variant,
    _draw,
    _pattern,
)


def _check(days: list[list[tuple[Pos, Pos]]], pots: int, size: int, per_pot: int) -> None:
    opponents: dict[Pos, list[Pos]] = defaultdict(list)
    homes: dict[Pos, Counter[int]] = defaultdict(Counter)
    for day in days:
        playing = [p for match in day for p in match]
        assert sorted(playing) == [(p, i) for p in range(pots) for i in range(size)]
        for home, away in day:
            opponents[home].append(away)
            opponents[away].append(home)
            homes[home][away[0]] += 1
    for place, others in opponents.items():
        assert len(set(others)) == len(others), f"{place} meets a club twice"
        assert place not in others
        assert Counter(o[0] for o in others) == {p: per_pot for p in range(pots)}
        if per_pot == 2:  # one home and one away against each pot
            assert all(homes[place][p] == 1 for p in range(pots)), (place, homes[place])
        else:
            assert sum(homes[place].values()) == len(others) // 2


@pytest.mark.parametrize("seed", range(8))
def test_two_pots_split_into_four_matchdays(seed: int) -> None:
    days = _block_variant(9, np.random.default_rng(seed))
    assert len(days) == 4 and all(len(d) == 9 for d in days)
    _check([list(d) for d in days], 2, 9, 2)
    assert _block_matchdays(9, 1, 0, 1) is not None  # the first variant found


@pytest.mark.parametrize("seed", range(25))
def test_the_champions_league_pattern(seed: int) -> None:
    comp = get_world().defs.continental["UCL"]
    days = _pattern(comp, np.random.default_rng(seed))
    assert len(days) == 8 and all(len(d) == 18 for d in days)
    _check(days, 4, 9, 2)


@pytest.mark.parametrize("seed", range(25))
def test_the_conference_league_pattern(seed: int) -> None:
    comp = get_world().defs.continental["UECL"]
    days = _pattern(comp, np.random.default_rng(seed))
    assert len(days) == 6 and all(len(d) == 18 for d in days)
    _check(days, 6, 6, 1)


@pytest.mark.parametrize("seed", range(10))
def test_clubs_are_placed_apart_from_their_countrymen(seed: int) -> None:
    comp = get_world().defs.continental["UCL"]
    rng = np.random.default_rng(seed)
    # A Champions League's worth of countries: England's six down to one-club countries.
    codes = (["ENG"] * 6 + ["ESP"] * 5 + ["ITA"] * 4 + ["GER"] * 4 + ["FRA"] * 3 + ["POR"] * 2
             + ["NED"] * 2 + ["BEL", "TUR", "CZE", "GRE", "NOR", "POL", "DEN", "AUT", "SCO",
                              "SUI", "CRO", "UKR"])
    clubs = list(range(100, 136))
    country = {c: codes[k] for k, c in enumerate(clubs)}
    # Dealt across the pots as coefficients spread a country's clubs (a pot can't hold five
    # of one country: within a pot each club meets two neighbours on a cycle of nine).
    order = [clubs[k] for k in rng.permutation(36)]
    order.sort(key=lambda c: country[c])
    pots: list[list[int]] = [order[k::4] for k in range(4)]
    days, layout = _draw(comp, pots, country, rng)
    assert [sorted(p) for p in layout] == [sorted(p) for p in pots]  # nobody changed pot
    met: dict[int, list[str]] = defaultdict(list)
    for day in days:
        for (hp, hi), (ap, ai) in day:
            home, away = layout[hp][hi], layout[ap][ai]
            met[home].append(country[away])
            met[away].append(country[home])
    for c, countries in met.items():
        assert country[c] not in countries
        assert max(Counter(countries).values()) <= 2
