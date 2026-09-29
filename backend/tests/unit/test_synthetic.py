"""Synthetic squads look like real ones: the requested quality is their overall, and each
position's attributes relate to it as real players' do."""

import numpy as np
import pytest

from footsim.defs.positions import PositionGroup
from footsim.domain.attributes import ATTRIBUTES
from footsim.match.synthetic import synthetic_squad
from footsim.world.context import World, get_world


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def _attr(player: object, name: str) -> float:
    return float(player.attrs[ATTRIBUTES.index(name)])  # type: ignore[attr-defined]


@pytest.mark.parametrize("quality", [58.0, 70.0, 82.0])
def test_quality_is_the_squads_overall(world: World, quality: float) -> None:
    overalls = []
    for club in range(1, 9):
        for player in synthetic_squad(world.defs, club, quality):
            group = world.defs.positions[player.primary_position].group
            overalls.append(float(world.model.group_overalls(player.attrs)[group]))
    assert abs(float(np.mean(overalls)) - quality) < 2.0


def test_positions_have_real_attribute_profiles(world: World) -> None:
    squads = [p for club in range(1, 9) for p in synthetic_squad(world.defs, club, 70.0)]
    by_group: dict[PositionGroup, list[object]] = {}
    for player in squads:
        by_group.setdefault(world.defs.positions[player.primary_position].group, []).append(player)

    def mean(group: PositionGroup, name: str) -> float:
        return float(np.mean([_attr(p, name) for p in by_group[group]]))

    # Real centre-backs are about as aggressive as their overall; forwards far less so.
    assert mean(PositionGroup.CB, "aggression") > mean(PositionGroup.ST, "aggression") + 5
    assert mean(PositionGroup.ST, "standing_tackle") < 45
    assert mean(PositionGroup.CB, "standing_tackle") > 60
    assert mean(PositionGroup.ST, "finishing") > mean(PositionGroup.CB, "finishing") + 25
