"""Saves written by an older build are upgraded in place on load."""

import shutil
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import inspect, text

from footsim.api.session import CareerSession
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


def test_version_5_gains_the_overall_trend(tmp_path: Path) -> None:
    """Saves from before the up/down arrow get each player's trend, starting level."""
    path = tmp_path / "v5.sqlite"
    engine = create_database(path)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE player_development DROP COLUMN trend"))
    write_meta(engine, {"schema_version": 5})
    engine.dispose()
    engine = open_database(path)
    assert migrate(engine) == 5
    with engine.connect() as conn:
        columns = {c["name"] for c in inspect(conn).get_columns("player_development")}
    assert "trend" in columns
    engine.dispose()


def test_version_7_gains_retirement(tmp_path: Path) -> None:
    """Saves from before retirement get the column, every player still playing."""
    path = tmp_path / "v7.sqlite"
    engine = create_database(path)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE player DROP COLUMN retired_on"))
    write_meta(engine, {"schema_version": 7})
    engine.dispose()
    engine = open_database(path)
    assert migrate(engine) == 7
    assert migrate(engine) == SCHEMA_VERSION  # and running it again changes nothing
    with engine.connect() as conn:
        columns = {c["name"] for c in inspect(conn).get_columns("player")}
    assert "retired_on" in columns
    engine.dispose()


def test_version_8_gains_the_season_overalls(tmp_path: Path) -> None:
    """Saves from before the season summary's development table get its record table. A world
    that isn't a career yet has no season to record."""
    path = tmp_path / "v8.sqlite"
    engine = create_database(path)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE player_season_overall"))
    write_meta(engine, {"schema_version": 8})
    engine.dispose()
    engine = open_database(path)
    assert migrate(engine) == 8
    assert migrate(engine) == SCHEMA_VERSION
    with engine.connect() as conn:
        assert "player_season_overall" in inspect(conn).get_table_names()
        assert conn.execute(text("SELECT COUNT(*) FROM player_season_overall")).scalar_one() == 0
    engine.dispose()


@pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
def test_version_8_starts_the_record_for_a_career_under_way(tmp_path: Path) -> None:
    """A career already under way has the current season recorded from the day it is upgraded
    (it can't know the season's start), once, for every player still playing."""
    session = CareerSession(tmp_path / "saves", BASE_WORLD)
    session.new_career(1, 218, "Upgrade")
    engine = session.engine
    with engine.begin() as conn:
        playing: int = conn.execute(text(
            "SELECT COUNT(*) FROM player WHERE retired_on IS NULL")).scalar_one()
        conn.execute(text("DROP TABLE player_season_overall"))
        conn.execute(text("UPDATE game_meta SET value = '\"2026-10-14\"' "
                          "WHERE key = 'game_date'"))
    write_meta(engine, {"schema_version": 8})
    assert migrate(engine) == 8
    for _ in range(2):  # and upgrading again changes nothing
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT season_id, recorded_on, COUNT(*) AS n FROM player_season_overall "
                "GROUP BY season_id, recorded_on")).all()
        assert [(r.season_id, r.recorded_on, r.n) for r in rows] == [(1, "2026-10-14", playing)]
        migrate(engine)
    session.close()
