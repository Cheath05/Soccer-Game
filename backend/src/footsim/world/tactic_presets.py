"""The user's saved tactics: name the tactic they have now and bring it back later.

A saved tactic is the formation, the roles and the team instructions, and the line-up too when
the user saves it with one. Loading one makes it the club's tactic (career.set_user_tactic,
with the same checks); players saved in its line-up who have left the club since are dropped,
and the rest of the line-up is picked automatically.
"""

import json
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Connection, select, text

from footsim.persistence.schema import tactic, tactic_preset
from footsim.world.career import set_user_tactic
from footsim.world.context import World
from footsim.world.meta import CareerMeta

MAX_PRESETS = 20
MAX_NAME = 40


class PresetRefused(Exception):
    """Why a tactic can't be saved or loaded (shown to the user)."""


@dataclass(frozen=True)
class Preset:
    id: int
    name: str
    formation: str
    with_lineup: bool
    saved: str


def presets(conn: Connection, meta: CareerMeta) -> list[Preset]:
    return [Preset(int(r.id), str(r.name), str(r.formation), r.lineup is not None, str(r.saved))
            for r in conn.execute(select(tactic_preset).where(
                tactic_preset.c.club_id == meta.user_club_id).order_by(tactic_preset.c.name))]


def save_preset(conn: Connection, meta: CareerMeta, name: str, with_lineup: bool,
                day: date) -> None:
    """Save the club's tactic now as ``name`` (a tactic saved under that name is replaced)."""
    name = name.strip()
    if not name or len(name) > MAX_NAME:
        raise PresetRefused(f"Give it a name of 1 to {MAX_NAME} characters.")
    row = conn.execute(select(tactic).where(tactic.c.club_id == meta.user_club_id)).first()
    if row is None:
        raise PresetRefused("Set up a tactic first.")
    exists = conn.execute(select(tactic_preset.c.id).where(
        tactic_preset.c.club_id == meta.user_club_id, tactic_preset.c.name == name)).first()
    if exists is None and len(presets(conn, meta)) >= MAX_PRESETS:
        raise PresetRefused(f"You can keep {MAX_PRESETS} tactics: delete one first.")
    conn.execute(text(
        "INSERT INTO tactic_preset (club_id, name, formation, roles, lineup, instructions, saved) "
        "VALUES (:c, :n, :f, :r, :l, :i, :d) ON CONFLICT(club_id, name) DO UPDATE SET "
        "formation = excluded.formation, roles = excluded.roles, lineup = excluded.lineup, "
        "instructions = excluded.instructions, saved = excluded.saved"),
        {"c": meta.user_club_id, "n": name, "f": row.formation, "r": row.roles,
         "l": row.lineup if with_lineup else None, "i": row.instructions,
         "d": day.isoformat()})


def load_preset(conn: Connection, world: World, meta: CareerMeta, preset_id: int) -> None:
    """Make a saved tactic the club's tactic."""
    row = conn.execute(select(tactic_preset).where(
        tactic_preset.c.id == preset_id, tactic_preset.c.club_id == meta.user_club_id)).first()
    if row is None:
        raise PresetRefused("No such saved tactic.")
    lineup = None
    if row.lineup is not None:
        squad = {int(r.person_id) for r in conn.execute(text(
            "SELECT person_id FROM playing WHERE club_id = :c"), {"c": meta.user_club_id})}
        kept = {k: int(v) for k, v in json.loads(row.lineup).items() if int(v) in squad}
        lineup = kept or None
    try:
        set_user_tactic(conn, world, row.formation, json.loads(row.roles), lineup,
                        json.loads(row.instructions))
    except ValueError as exc:  # e.g. a formation or role since removed from the game
        raise PresetRefused(str(exc)) from exc


def delete_preset(conn: Connection, meta: CareerMeta, preset_id: int) -> None:
    conn.execute(tactic_preset.delete().where(
        tactic_preset.c.id == preset_id, tactic_preset.c.club_id == meta.user_club_id))
