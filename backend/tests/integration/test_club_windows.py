"""Whose transfer windows a club follows (W4-2): its league's country, else its own.

Skipped when the base world hasn't been built (it needs the locally downloaded EA FC 27 file,
which isn't in the repository)."""

import shutil
from pathlib import Path

import pytest
from sqlalchemy import text

from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.world.career import initialize_career
from footsim.world.context import get_world
from footsim.world.windows import club_window_nation

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


def test_a_club_follows_its_leagues_country_or_its_own(tmp_path: Path) -> None:
    path = tmp_path / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, get_world(), None, None, seed=5)
    with engine.connect() as conn:
        in_league = conn.execute(text(
            "SELECT m.club_id, n.code FROM club_league_membership m "
            "JOIN competition c ON c.id = m.competition_id JOIN nation n ON n.id = c.nation_id "
            "WHERE m.season_id = 1")).all()
        for r in in_league[::25]:
            assert club_window_nation(conn, r.club_id, 1) == r.code
        outside = conn.execute(text(
            "SELECT k.id, n.code FROM club k JOIN nation n ON n.id = k.nation_id "
            "WHERE k.id NOT IN (SELECT club_id FROM club_league_membership WHERE season_id = 1) "
            "LIMIT 20")).all()
        assert outside
        for r in outside:
            assert club_window_nation(conn, r.id, 1) == r.code
    engine.dispose()
