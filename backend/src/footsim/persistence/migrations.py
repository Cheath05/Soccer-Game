"""Forward migrations for save databases.

Each step upgrades a database from one schema version to the next. Loading a save runs the
missing steps on its working copy (the saved file itself is untouched until the next save),
so careers survive upgrades. Steps must be idempotent: a step that half-ran before a crash
has to be safe to run again.
"""

import json
from collections.abc import Callable

import numpy as np
from sqlalchemy import Connection, Engine, inspect, select, text

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
    """Cup ties. A career already under way starts its cups this season if their first round
    is still to come (its league matches are moved around the ties), or else next season."""
    metadata.create_all(conn)


def _to_v8(conn: Connection) -> None:
    """Retirement: the day a player retired."""
    _add_column(conn, "player", "retired_on", "TEXT")


def _to_v9(conn: Connection) -> None:
    """Each player's overall as a season began, for the season summary's development table. A
    career already under way starts the record from today, as it can't know the season's start
    (the summary says so); a world that isn't a career yet has nothing to record."""
    from footsim.world.context import get_world
    from footsim.world.meta import read_meta as read_career
    from footsim.world.overall_history import record_season_start

    metadata.create_all(conn)
    if conn.execute(select(game_meta.c.key).where(game_meta.c.key == "user_club_id")).first():
        meta = read_career(conn)
        record_season_start(conn, get_world(), meta.season_id, meta.current_date)


def _to_v10(conn: Connection) -> None:
    """Club finances (W3). A career already under way gets them from today, as if they began
    now: each club's own income from its current wage bill, the budgets for the rest of this
    season. A world that isn't a career yet gets them when a career starts."""
    from footsim.world.context import get_world
    from footsim.world.finance import initialize_finances
    from footsim.world.meta import read_meta as read_career

    metadata.create_all(conn)
    if conn.execute(select(game_meta.c.key).where(game_meta.c.key == "user_club_id")).first():
        meta = read_career(conn)
        initialize_finances(conn, get_world(), meta, meta.current_date)


# target version -> step that upgrades from the version before it
def _to_v11(conn: Connection) -> None:
    """The transfer market (W4-3): its history and offers, transfer-listing, players' market
    premiums, and one club per player made a rule. A player can't have two active contracts
    that aren't loans; should a save hold any (it shouldn't), the latest one is kept. A career
    already under way gets the premiums from today."""
    from footsim.world.context import get_world
    from footsim.world.meta import read_meta as read_career
    from footsim.world.transfers import initialize_value_premiums

    metadata.create_all(conn)
    _add_column(conn, "contract", "listed", "INTEGER NOT NULL DEFAULT 0")
    _add_column(conn, "player", "value_premium", "REAL")
    doubled: list[int] = list(conn.execute(text(
        "SELECT person_id FROM contract WHERE is_active = 1 AND kind != 'loan' "
        "GROUP BY person_id HAVING COUNT(*) > 1 ORDER BY person_id")).scalars())
    for person_id in doubled:
        rows: list[int] = list(conn.execute(text(
            "SELECT id FROM contract WHERE person_id = :p AND is_active = 1 AND kind != 'loan' "
            "ORDER BY start_date DESC, id DESC"), {"p": person_id}).scalars())
        conn.execute(text("UPDATE contract SET is_active = 0 WHERE id = :id"),
                     [{"id": stale} for stale in rows[1:]])
    conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_contract_owner ON contract (person_id) "
        "WHERE is_active = 1 AND kind != 'loan'"))
    if conn.execute(select(game_meta.c.key).where(game_meta.c.key == "user_club_id")).first():
        meta = read_career(conn)
        initialize_value_premiums(conn, get_world(), meta.current_date)


def _to_v12(conn: Connection) -> None:
    """Development rewards a place in the first team: the bench minutes a player is credited
    for being named a substitute without coming on, and the potential the academy boost has
    added. Both start at 0 in a save under way (nobody has been credited yet)."""
    metadata.create_all(conn)  # a world that never had the development table gets it whole
    _add_column(conn, "player_state", "bench_minutes", "REAL NOT NULL DEFAULT 0")
    _add_column(conn, "player_development", "potential_boost", "REAL NOT NULL DEFAULT 0")


def _to_v13(conn: Connection) -> None:
    """Loans (W4-8): at most one active loan per player, and the ``playing`` view (where each
    player plays) that every squad reads."""
    from footsim.persistence.schema import PLAYING_VIEW

    metadata.create_all(conn)
    conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_contract_loan ON contract (person_id) "
        "WHERE is_active = 1 AND kind = 'loan'"))
    conn.execute(text(PLAYING_VIEW))


def _to_v14(conn: Connection) -> None:
    """Real names for the clubs the source data lists under made-up ones (AC Milan, Inter,
    Atalanta, Lazio): data/config/world/club_names.yaml, renamed by the old name."""
    from footsim.world.club_names import apply_club_names

    apply_club_names(conn)


STEPS: dict[int, Callable[[Connection], None]] = {
    3: _to_v3, 4: _to_v4, 5: _to_v5, 6: _to_v6, 7: _to_v7, 8: _to_v8, 9: _to_v9, 10: _to_v10,
    11: _to_v11, 12: _to_v12, 13: _to_v13, 14: _to_v14}


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
