"""SQLite engine creation with the pragmas every connection needs."""

import json
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.pool import ConnectionPoolEntry

from footsim.persistence.schema import SCHEMA_VERSION, game_meta, metadata


def _set_pragmas(dbapi_conn: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")
    # Never run SQL functions embedded in schema objects of a possibly shared save.
    cursor.execute("PRAGMA trusted_schema = OFF")
    cursor.close()


def open_database(path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{path}")
    event.listen(engine, "connect", _set_pragmas)
    return engine


def create_database(path: Path) -> Engine:
    """Create a new, empty database file with the current schema."""
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = open_database(path)
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(game_meta.insert(), [{"key": "schema_version", "value": str(SCHEMA_VERSION)}])
    return engine


def write_meta(engine: Engine, values: dict[str, Any]) -> None:
    with engine.begin() as conn:
        for key, value in values.items():
            conn.execute(game_meta.delete().where(game_meta.c.key == key))
            conn.execute(game_meta.insert(), [{"key": key, "value": json.dumps(value)}])


def read_meta(engine: Engine) -> dict[str, Any]:
    with engine.connect() as conn:
        rows = conn.execute(select(game_meta.c.key, game_meta.c.value)).all()
    return {key: json.loads(value) for key, value in rows}
