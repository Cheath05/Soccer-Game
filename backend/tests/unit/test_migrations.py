"""Saves written by an older build are upgraded in place on load."""

import shutil
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import inspect, text

from footsim.core.paths import data_dir
from footsim.persistence.database import (
    SchemaMismatch,
    create_database,
    open_database,
    read_meta,
    write_meta,
)
from footsim.persistence.migrations import migrate
from footsim.persistence.schema import SCHEMA_VERSION


def _v2_database(path: Path) -> None:
    """A database as version 2 wrote it: match events without period/second."""
    engine = create_database(path)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE match_event DROP COLUMN period"))
        conn.execute(text("ALTER TABLE match_event DROP COLUMN second"))
    write_meta(engine, {"schema_version": 2})
    engine.dispose()


def test_version_2_is_upgraded(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite"
    _v2_database(path)
    engine = open_database(path)
    assert migrate(engine) == 2
    assert read_meta(engine)["schema_version"] == SCHEMA_VERSION
    with engine.connect() as conn:
        columns = {c["name"] for c in inspect(conn).get_columns("match_event")}
    assert {"period", "second"} <= columns
    assert migrate(engine) == SCHEMA_VERSION  # nothing left to do
    engine.dispose()


def test_newer_databases_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite"
    engine = create_database(path)
    write_meta(engine, {"schema_version": SCHEMA_VERSION + 1})
    with pytest.raises(SchemaMismatch):
        migrate(engine)
    engine.dispose()


def test_version_3_gains_player_development(tmp_path: Path) -> None:
    """Saves from before monthly development traits get the table when loaded (1 Oct)."""
    path = tmp_path / "v3.sqlite"
    engine = create_database(path)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE player_development"))
    write_meta(engine, {"schema_version": 3})
    engine.dispose()
    engine = open_database(path)
    assert migrate(engine) == 3
    with engine.connect() as conn:
        assert "player_development" in inspect(conn).get_table_names()
    engine.dispose()


BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"


@pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
def test_version_4_moves_potential_with_the_new_overall(tmp_path: Path) -> None:
    """Overalls count every headline rating from v5 (P14): each player's hidden potential moves
    with his overall, so his room to grow is unchanged, and it moves only once."""
    path = tmp_path / "v4.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    write_meta(engine, {"schema_version": 4})
    with engine.connect() as conn:
        before = dict(conn.execute(text("SELECT person_id, pa_hidden FROM player")).all())
    migrate(engine)
    with engine.connect() as conn:
        after = dict(conn.execute(text("SELECT person_id, pa_hidden FROM player")).all())
    shifts = np.array([after[p] - before[p] for p in before])
    assert abs(shifts.mean()) < 0.5  # each group's average overall is unchanged...
    assert (shifts != 0).mean() > 0.5  # ...but most players' overall moved
    assert np.abs(shifts).max() <= 10
    assert read_meta(engine)["schema_version"] == SCHEMA_VERSION
    migrate(engine)  # loading it again changes nothing
    with engine.connect() as conn:
        again = dict(conn.execute(text("SELECT person_id, pa_hidden FROM player")).all())
    assert again == after
    engine.dispose()
