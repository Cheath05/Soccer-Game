"""Per-entity random streams for world building (see footsim.core.rng)."""

import numpy as np

from footsim.core.rng import derive_rng


def entity_rng(seed: int, source: str, entity_id: str, purpose: str) -> np.random.Generator:
    return derive_rng(seed, source, entity_id, purpose)
