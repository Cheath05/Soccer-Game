"""The W9a format pieces on their own: series, reseeded picks, group seeds, phase splits and the
definitions' checks."""

from collections import Counter

import numpy as np
import pytest
from pydantic import ValidationError

from footsim.competitions.fixtures import balance_venues, grouped_rounds, split_phases
from footsim.competitions.playoffs import Entrant, Seeds, legs_for, round_ties, series_winner
from footsim.defs.competitions import LeagueDef, PlayoffDef, PlayoffRoundDef


def test_a_series_is_won_by_the_first_to_a_majority() -> None:
    assert series_winner(1, 2, 3, [(1, 2, 2, 0, None, None)]) is None
    assert series_winner(1, 2, 3, [(1, 2, 2, 0, None, None), (2, 1, 1, 1, 4, 5)]) == 1
    assert series_winner(1, 2, 3, [(1, 2, 0, 1, None, None), (2, 1, 3, 0, None, None)]) == 2


def test_the_better_seed_hosts_a_series_odd_games() -> None:
    rnd = PlayoffRoundDef.model_validate({"name": "R1", "games": 3, "ties": [
        {"id": "T", "a": {"rank": 1}, "b": {"rank": 8}}]})
    tie = round_ties(PlayoffDef(key="P", name="P", rounds=[
        rnd.model_copy(update={"ties": [rnd.ties[0]]})]), 0, {1: 10, 8: 80}, {})[0]
    assert [(g.home, g.leg) for g in legs_for(tie, rnd)] == [(10, 1), (80, 2), (10, 3)]


def test_reseeded_picks_and_group_ranks() -> None:
    seeds = Seeds.of([5, 6, 7, 8, 9], {"E": {6, 8}, "W": {5, 7, 9}})
    assert seeds.groups == {"E": {1: 6, 2: 8}, "W": {1: 5, 2: 7, 3: 9}}
    playoff = PlayoffDef.model_validate({"key": "P", "name": "P", "rounds": [
        {"name": "A", "ties": [{"id": f"Q{k}", "a": {"rank": k}, "b": {"rank": k}}
                               for k in range(1, 2)]},
        {"name": "B", "ties": [
            {"id": "S1", "a": {"winner_of": ["Q1"]}, "b": {"group": "W", "rank": 3}}]}]})
    ties = round_ties(playoff, 1, seeds, {"Q1": Entrant(6, 2)})
    assert (ties[0].a.club_id, ties[0].b.club_id) == (6, 9)
    winners = {f"Q{k}": Entrant(100 + k, r) for k, r in enumerate((1, 3, 6, 8), start=1)}
    quarters = {"name": "Q", "ties": [{"id": f"Q{k}", "a": {"rank": k}, "b": {"rank": 9 - k}}
                                      for k in range(1, 5)]}
    semis = PlayoffDef.model_validate({"key": "P", "name": "P", "rounds": [
        quarters, {"name": "S", "ties": [
        {"id": "S1", "a": {"winner_of": list(winners), "pick": "highest_ranked"},
         "b": {"winner_of": list(winners), "pick": "lowest_ranked"}},
        {"id": "S2", "a": {"winner_of": list(winners), "pick": "second_highest"},
         "b": {"winner_of": list(winners), "pick": "second_lowest"}}]},
        {"name": "F", "ties": [{"id": "F", "a": {"winner_of": ["S1"]},
                                "b": {"winner_of": ["S2"]}}]}]})
    got = [(t.a.rank, t.b.rank) for t in round_ties(semis, 1, {}, winners)]
    assert got == [(1, 8), (3, 6)]


def test_phases_split_evenly_and_venues_balance() -> None:
    assert split_phases([[], [], [], []], 2) == [[[], []], [[], []]]
    with pytest.raises(ValueError):
        split_phases([[], [], []], 2)
    games = balance_venues([[(1, 2), (3, 4)], [(1, 3), (2, 4)], [(1, 4), (2, 3)],
                            [(2, 1), (4, 3)]])
    home = Counter(h for rnd in games for h, _ in rnd)
    assert set(home.values()) == {2}
    rounds = grouped_rounds([[1, 2, 3], [4, 5, 6]], 2, 2, [], 1, np.random.default_rng(0))[0]
    meetings = Counter(frozenset(g) for rnd in rounds for g in rnd)
    assert sum(1 for m in meetings if len(m & {1, 2, 3}) == 1) == 6  # two each, all distinct


def _league(**extra: object) -> dict[str, object]:
    return {"key": "X", "name": "X", "short_name": "X", "nation": "USA", "tier": 1, "clubs": 4,
            "calendar": "C", "tiebreakers": ["points"], **extra}


def test_definitions_reject_bad_groups_and_phases() -> None:
    groups = [{"key": "E", "name": "E", "clubs": ["a", "b"]},
              {"key": "W", "name": "W", "clubs": ["c", "d"]}]
    LeagueDef.model_validate(_league(format={"type": "groups", "cross_rounds": 1},
                                     groups=groups))
    with pytest.raises(ValidationError):  # groups without a groups format
        LeagueDef.model_validate(_league(groups=groups))
    with pytest.raises(ValidationError):  # a club missing from the groups
        LeagueDef.model_validate(_league(format={"type": "groups"}, groups=groups[:1]))
    with pytest.raises(ValidationError):  # rivals from one group
        LeagueDef.model_validate(_league(format={"type": "groups", "cross_rounds": 1,
                                                 "rivals": [["a", "b"]]}, groups=groups))
    playoff = {"key": "P", "name": "P", "rounds": [{"name": "F", "ties": [
        {"id": "F", "a": {"rank": 1}, "b": {"rank": 2}}]}]}
    with pytest.raises(ValidationError):  # a phased league's play-off must name its phase
        LeagueDef.model_validate(_league(phases=[{"key": "AP", "name": "Apertura"}],
                                         playoffs=[playoff]))
    with pytest.raises(ValidationError):  # a series at a neutral ground
        PlayoffRoundDef.model_validate({"name": "R", "games": 3, "host": "neutral", "ties": []})
