"""Every formation in data/config/formations plays: its slots are filled sensibly and a match
runs in it without trouble (the user picks them on the tactics screen and during matches)."""

import numpy as np
import pytest

from footsim.core.rng import derive_rng
from footsim.match.engine.engine import MatchEngine
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import World, get_world

WORLD = get_world()


@pytest.mark.parametrize("key", sorted(WORLD.defs.formations))
def test_a_match_plays_in_every_formation(key: str) -> None:
    world: World = WORLD
    home = synthetic_sheet(world.defs, world.picker, 1, 72, formation=key)
    away = synthetic_sheet(world.defs, world.picker, 2, 72, formation="4-4-2")
    assert {sp.slot for sp in home.starters} == {s.id for s in world.defs.formations[key].slots}
    assert all(sp.rating > 40 for sp in home.starters)  # nobody wildly out of position
    engine = MatchEngine(world.defs, home, away, derive_rng(1, f"formation-{key}"), record=False)
    engine.run(max_ticks=3000)  # five minutes
    assert np.isfinite(engine.pos).all()
    assert engine.stats[0].passes > 0
