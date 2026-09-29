"""Forward migrations for save databases.

Each step upgrades a database from one schema version to the next. Loading a save runs the
missing steps on its working copy (the saved file itself is untouched until the next save),
so careers survive upgrades. Steps must be idempotent: a step that half-ran before a crash
has to be safe to run again.
"""

from collections.abc import Callable

from sqlalchemy import Connection, Engine, inspect, text

from footsim.persistence.database import SchemaMismatch, read_meta, write_meta
from footsim.persistence.schema import SCHEMA_VERSION, metadata


def _add_column(conn: Connection, table: str, column: str, sql_type: str) -> None:
    existing = {c["name"] for c in inspect(conn).get_columns(table)}
    if column not in existing:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))


def _to_v3(conn: Connection) -> None:
    """Match events are timed to the second within their period."""
    metadata.create_all(conn)  # runtime tables a very old world may lack
    _add_column(conn, "match_event", "period", "INTEGER")
    _add_column(conn, "match_event", "second", "INTEGER")


# target version -> step that upgrades from the version before it
STEPS: dict[int, Callable[[Connection], None]] = {3: _to_v3}


def migrate(engine: Engine) -> int:
    """Bring a database up to SCHEMA_VERSION; returns the version it started at."""
    version = read_meta(engine).get("schema_version")
    if not isinstance(version, int) or version > SCHEMA_VERSION:
        raise SchemaMismatch(
            f"database schema v{version} is newer than this build (v{SCHEMA_VERSION}) "
            "or unreadable")
    start = version
    while version < SCHEMA_VERSION:
        step = STEPS.get(version + 1)
        if step is None:
            raise SchemaMismatch(
                f"database schema v{version} can't be upgraded to v{SCHEMA_VERSION}: rebuild "
                "the world with `just build-world --force` and start a new career")
        with engine.begin() as conn:
            step(conn)
        version += 1
        write_meta(engine, {"schema_version": version})
    return start
