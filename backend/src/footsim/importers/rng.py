"""Deterministic per-entity random streams for world building.

Each (world seed, source, entity id, purpose) gets its own generator, so results don't
depend on processing order and adding a new random draw elsewhere changes nothing else.
"""

import hashlib

import numpy as np


def entity_rng(seed: int, source: str, entity_id: str, purpose: str) -> np.random.Generator:
    digest = hashlib.blake2b(f"{source}|{entity_id}|{purpose}".encode(), digest_size=8).digest()
    return np.random.default_rng([seed, int.from_bytes(digest, "little")])
