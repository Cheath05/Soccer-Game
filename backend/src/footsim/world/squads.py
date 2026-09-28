"""Loading squads and team sheets from the save database."""

import json
from collections import defaultdict
from datetime import date

import numpy as np
from sqlalchemy import Connection, select, text

from footsim.domain.attributes import ATTRIBUTES
from footsim.importers.generate import age_on
from footsim.match.teams import SquadPlayer, TeamSheet
from footsim.persistence.schema import club, player_attr, player_position, tactic
from footsim.world.context import World, default_instructions

_SQUAD_SQL = text("""
    SELECT p.id, p.first_name, p.last_name, p.known_as, p.birth_date,
           pl.height_cm, pl.preferred_foot, pl.weak_foot,
           s.condition, s.injured_until, s.suspended_matches
    FROM contract k
    JOIN person p ON p.id = k.person_id
    JOIN player pl ON pl.person_id = p.id
    LEFT JOIN player_state s ON s.player_id = p.id
    WHERE k.club_id = :club AND k.is_active = 1
""")


def display_name(first: str, last: str, known_as: str | None) -> str:
    return known_as or f"{first} {last}".strip()


def short_name(first: str, last: str, known_as: str | None) -> str:
    if known_as:
        return known_as
    return last if len(last) <= 14 else last.split()[0]


def load_squad(conn: Connection, club_id: int, day: date) -> list[SquadPlayer]:
    rows = conn.execute(_SQUAD_SQL, {"club": club_id}).all()
    ids = [r.id for r in rows]
    if not ids:
        return []
    attrs = {
        r.player_id: np.array([getattr(r, a) for a in ATTRIBUTES], dtype=np.float64)
        for r in conn.execute(select(player_attr).where(player_attr.c.player_id.in_(ids)))
    }
    positions: dict[int, dict[str, int]] = defaultdict(dict)
    for r in conn.execute(select(player_position).where(player_position.c.player_id.in_(ids))):
        positions[r.player_id][r.position] = r.familiarity
    squad = []
    for r in rows:
        fams = positions[r.id]
        injured = r.injured_until is not None and date.fromisoformat(r.injured_until) > day
        squad.append(SquadPlayer(
            player_id=r.id,
            name=display_name(r.first_name, r.last_name, r.known_as),
            short_name=short_name(r.first_name, r.last_name, r.known_as),
            primary_position=max(fams, key=lambda pos: fams[pos]) if fams else "CM",
            positions=fams,
            attrs=attrs[r.id],
            condition=float(r.condition if r.condition is not None else 100.0),
            available=not injured and not (r.suspended_matches or 0),
            height_cm=r.height_cm or 180,
            preferred_foot=r.preferred_foot,
            weak_foot=r.weak_foot,
            age=age_on(date.fromisoformat(r.birth_date), day),
        ))
    return squad


def club_name(conn: Connection, club_id: int) -> str:
    return str(conn.execute(select(club.c.name).where(club.c.id == club_id)).scalar_one())


def team_sheet(conn: Connection, world: World, club_id: int, day: date) -> TeamSheet:
    squad = load_squad(conn, club_id, day)
    row = conn.execute(select(tactic).where(tactic.c.club_id == club_id)).first()
    instructions = default_instructions(world.defs)
    formation_key, roles, lineup = "4-3-3", {}, None
    if row is not None:
        formation_key = row.formation
        roles = json.loads(row.roles)
        lineup = {k: int(v) for k, v in json.loads(row.lineup).items()} if row.lineup else None
        instructions.update(json.loads(row.instructions))
    return world.picker.pick(
        club_id, club_name(conn, club_id), squad, world.defs.formations[formation_key],
        roles=roles, fixed=lineup, instructions=instructions,
    )
