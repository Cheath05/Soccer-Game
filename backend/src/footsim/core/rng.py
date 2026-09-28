"""Deterministic random streams.

Every consumer derives its own generator from the world seed plus a few identifying parts
(e.g. ``derive_rng(seed, "match", fixture_id)``), so results never depend on the order in
which things are processed, and adding a draw in one system never shifts another.
"""

import hashlib

import numpy as np


def derive_seed(seed: int, *parts: object) -> int:
    key = "|".join(str(p) for p in parts).encode()
    return int.from_bytes(hashlib.blake2b(key, digest_size=8).digest(), "little") ^ seed


def derive_rng(seed: int, *parts: object) -> np.random.Generator:
    key = "|".join(str(p) for p in parts).encode()
    digest = int.from_bytes(hashlib.blake2b(key, digest_size=8).digest(), "little")
    return np.random.default_rng([seed, digest])
