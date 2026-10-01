"""Line-up selection: fixing a player in a slot decides who plays there, never how good he is."""

import pytest

from footsim.match.synthetic import synthetic_squad
from footsim.world.context import World, get_world


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def test_a_fixed_player_keeps_his_real_slot_rating(world: World) -> None:
    """The user's hand-picked line-up showed every starter as 99 (30 Sep play-test): the score
    that forces a fixed player into his slot was reported as his rating."""
    squad = synthetic_squad(world.defs, 1, 70.0)
    shape = world.defs.formations["4-3-3"]
    auto = world.picker.pick(1, "Club 1", squad, shape)
    # As the tactics screen sends it: every slot fixed, with one substitute swapped in.
    lineup = {sp.slot: sp.player_id for sp in auto.starters if sp.slot is not None}
    lineup[auto.starters[-1].slot or ""] = auto.bench[0].player_id

    sheet = world.picker.pick(1, "Club 1", squad, shape, fixed=lineup)

    assert {sp.slot: sp.player_id for sp in sheet.starters} == lineup
    for sp in sheet.starters:
        real = world.picker.slot_rating(sp.player, sp.position, sp.role)
        assert sp.rating == pytest.approx(min(real, 99.0))
        assert sp.rating < 99.0
