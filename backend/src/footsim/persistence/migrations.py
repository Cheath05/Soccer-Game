"""Forward migrations for save databases.

Each step upgrades a database from one schema version to the next. Loading a save runs the
missing steps on its working copy (the saved file itself is untouched until the next save),
so careers survive upgrades. Steps must be idempotent: a step that half-ran before a crash
has to be safe to run again.
"""

import json
from collections.abc import Callable

import numpy as np
from sqlalchemy import Connection, Engine, inspect, text

from footsim.persistence.database import SchemaMismatch, read_meta, write_meta
from footsim.persistence.schema import SCHEMA_VERSION, game_meta, metadata


def _add_column(conn: Connection, table: str, column: str, sql_type: str) -> None:
    existing = {c["name"] for c in inspect(conn).get_columns(table)}
    if column not in existing:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))


def _to_v3(conn: Connection) -> None:
    """Match events are timed to the second within their period."""
    metadata.create_all(conn)  # runtime tables a very old world may lack
    _add_column(conn, "match_event", "period", "INTEGER")
    _add_column(conn, "match_event", "second", "INTEGER")


def _to_v4(conn: Connection) -> None:
    """Players' development traits and progress (rows are drawn the first time they're needed)."""
    metadata.create_all(conn)


# The overall scaling before P14 (calibration/overall_scaling.yaml at 578342d), for _to_v5.
_SCALING_BEFORE_V5 = {
    "GK": (0.9958, 1.553), "CB": (0.9981, -0.032), "FB": (0.9740, 2.156),
    "DM": (0.9475, 4.850), "CM": (0.9650, 1.985), "AM": (0.9461, 3.830),
    "W": (1.0185, -2.498), "ST": (0.9916, -0.273),
}


def _to_v5(conn: Connection) -> None:
    """Overalls now count all six headline ratings (P14), so a player's overall moves by a few
    points. His hidden potential moves with it, keeping the same room to grow."""
    from footsim.domain.attributes import ATTRIBUTES
    from footsim.ratings.overall import GroupScaling, OverallScaling, RatingModel
    from footsim.world.context import get_world

    world = get_world()
    before = RatingModel.build(world.defs, OverallScaling.model_validate({"groups": {
        g: GroupScaling(scale=scale, offset=offset)
        for g, (scale, offset) in _SCALING_BEFORE_V5.items()}}), face_blend=0.0)
    rows = conn.execute(text("""
        SELECT a.*, p.pa_hidden,
               (SELECT position FROM player_position pp WHERE pp.player_id = a.player_id
                ORDER BY familiarity DESC LIMIT 1) AS primary_position
        FROM player_attr a JOIN player p ON p.person_id = a.player_id""")).all()
    if rows:
        attrs = np.array([[getattr(r, a) for a in ATTRIBUTES] for r in rows], dtype=float)
        old, new = before.group_overalls(attrs), world.model.group_overalls(attrs)
        updates = []
        for i, r in enumerate(rows):
            group = world.defs.positions[r.primary_position or "CM"].group
            shifted = round(r.pa_hidden + new[group][i] - old[group][i])
            updates.append({"pid": r.player_id, "pa": int(np.clip(shifted, 1, 99))})
        conn.execute(text("UPDATE player SET pa_hidden = :pa WHERE person_id = :pid"), updates)
    # Recorded in the same transaction, so a crash can't leave potentials shifted twice.
    conn.execute(game_meta.delete().where(game_meta.c.key == "schema_version"))
    conn.execute(game_meta.insert(), [{"key": "schema_version", "value": json.dumps(5)}])


def _to_v6(conn: Connection) -> None:
    """Each player's recent overall trend, for the up/down arrow by his overall."""
    metadata.create_all(conn)  # a world that never had the development table gets it whole
    _add_column(conn, "player_development", "trend", "REAL NOT NULL DEFAULT 0")


def _to_v7(conn: Connection) -> None:
    """Cup ties. A career already under way gets its cups from its next season, when its
    league fixtures are scheduled around them."""
    metadata.create_all(conn)


# target version -> step that upgrades from the version before it
STEPS: dict[int, Callable[[Connection], None]] = {
    3: _to_v3, 4: _to_v4, 5: _to_v5, 6: _to_v6, 7: _to_v7}


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
