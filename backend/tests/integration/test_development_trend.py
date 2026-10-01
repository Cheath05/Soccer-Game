"""The up/down arrow by a player's overall (P15): it follows his recent development, so young
players show it rising and old ones falling. Skipped when the base world hasn't been built
(it needs the locally downloaded EA FC 27 file, which isn't in the repository)."""

from datetime import date
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import text

from footsim.api.session import CareerSession
from footsim.core.paths import data_dir
from footsim.world.context import get_world
from footsim.world.meta import read_meta
from footsim.world.season import develop_players

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


def test_trend_follows_development_by_age(tmp_path: Path) -> None:
    world = get_world()
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    session.new_career(1, 218, "Trend")
    with session.write() as conn:
        meta = read_meta(conn)
        for month in (8, 9, 10, 11, 12):
            develop_players(conn, world, meta, date(2026, month, 1), 1 / 12)
        rows = conn.execute(text("""SELECT d.trend, p.birth_date FROM player_development d
                                    JOIN person p ON p.id = d.player_id""")).all()
    trend = np.array([r.trend for r in rows])
    age = np.array([(date(2026, 12, 1) - date.fromisoformat(r.birth_date)).days / 365.25
                    for r in rows])
    shown = world.defs.development.trend_shown
    young, prime, old = trend[age < 21], trend[(age >= 25) & (age < 29)], trend[age >= 35]
    assert young.mean() > shown / 2 and np.mean(young <= -shown) < 0.02
    assert old.mean() < -shown / 2 and np.mean(old >= shown) < 0.02
    assert np.mean(np.abs(prime) >= shown) < 0.15  # most in their prime show no arrow
