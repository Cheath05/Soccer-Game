"""Every player's overall as each season began, kept so the season summary can show how the
user's players developed. A season's row is taken on its first day (at the career's start and at
each rollover, after the season's retirements and youth intake), so the next season's row is
also his overall at the end of this one."""

from collections.abc import Sequence
from datetime import date

import numpy as np
from sqlalchemy import Connection, select, text

from footsim.domain.attributes import ATTRIBUTES
from footsim.persistence.schema import player, player_attr, player_position
from footsim.world.context import World


def primary_positions(conn: Connection, ids: Sequence[int] | None = None) -> dict[int, str]:
    """Each player's best position (the alphabetically first of equals, as the squad page
    picks it); every player, or just ``ids``."""
    query = select(player_position).order_by(player_position.c.player_id,
                                             player_position.c.position)
    if ids is not None:
        query = query.where(player_position.c.player_id.in_(ids))
    best: dict[int, tuple[int, str]] = {}
    for r in conn.execute(query):
        if r.player_id not in best or r.familiarity > best[r.player_id][0]:
            best[r.player_id] = (r.familiarity, r.position)
    return {pid: position for pid, (_, position) in best.items()}


def player_overalls(conn: Connection, world: World, ids: Sequence[int] | None = None
                    ) -> dict[int, int]:
    """Each player's overall now, in the group of his best position, rounded as the squad page
    shows it: every player still playing, or just ``ids`` (retired ones too)."""
    query = select(player_attr)
    if ids is None:
        query = query.join(player, player.c.person_id == player_attr.c.player_id).where(
            player.c.retired_on.is_(None))
    else:
        query = query.where(player_attr.c.player_id.in_(ids))
    rows = conn.execute(query).all()
    if not rows:
        return {}
    positions = primary_positions(conn, ids)
    groups = world.model.group_overalls(
        np.array([[getattr(r, a) for a in ATTRIBUTES] for r in rows], dtype=float))
    return {r.player_id: round(float(
        groups[world.defs.positions[positions.get(r.player_id, "CM")].group][i]))
        for i, r in enumerate(rows)}


def record_season_start(conn: Connection, world: World, season_id: int, day: date) -> None:
    """Note every player's overall as ``season_id`` begins. A season already recorded for a
    player keeps its first row."""
    rows = [{"season": season_id, "pid": pid, "overall": overall, "day": day.isoformat()}
            for pid, overall in sorted(player_overalls(conn, world).items())]
    if rows:
        conn.execute(text(
            "INSERT OR IGNORE INTO player_season_overall (season_id, player_id, overall, "
            "recorded_on) VALUES (:season, :pid, :overall, :day)"), rows)
