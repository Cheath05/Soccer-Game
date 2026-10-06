"""Careers ending (W1): who retires at a season's end."""

import pytest

from footsim.world.context import World, get_world
from footsim.world.lifecycle import retirement_chance


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def test_players_retire_from_their_thirties_keepers_later(world: World) -> None:
    def chance(age: float, keeper: bool = False, overall: float = 70.0, ageless: bool = False,
               free: bool = False) -> float:
        return retirement_chance(world, age, keeper, overall, ageless, free)

    assert chance(29) == 0.0
    assert 0 < chance(33) < chance(35) < chance(37) < chance(40) <= 1.0
    assert chance(35, keeper=True) < chance(35)  # keepers play on
    assert chance(36, ageless=True) < chance(36)  # so do the rare ageless
    assert chance(36, overall=82) < chance(36) < chance(36, overall=50)
    assert chance(24, free=True) == world.defs.lifecycle.retirement.free_agent_leave
