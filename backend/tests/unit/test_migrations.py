"""Saves written by an older build are upgraded in place on load."""

from pathlib import Path

import pytest
from sqlalchemy import inspect, text

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
