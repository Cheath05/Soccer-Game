"""The user as a national team's manager (W8 I5), alongside his club.

Any nation's job can be taken (a sandbox choice for now) and left at any time. The user picks the
squad from the nation's eligible players (its made-up home-based pool and the players of its
nationality), up to the places of rules.yaml ``places``; it stays until he changes it, and is
picked for him (as an AI manager would) when it is empty at a call-up. He sets the team's tactics
on the Tactics page and plays its matches as his own (world/career.py ``user_teams``).
"""

import json
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Connection, text

from footsim.persistence.schema import national_squad
from footsim.world.context import World
from footsim.world.international.teams import nation_candidates, pick_squads
from footsim.world.meta import CareerMeta, write_meta


class JobRefused(ValueError):
    """The job can't be taken, or the squad isn't valid."""


@dataclass
class Candidate:
    player_id: int
    position: str
    overall: float
    selected: bool


def squad_size(world: World) -> int:
    return sum(starters + reserves
               for starters, reserves in world.defs.international.rules.places.values())


def nation_code(conn: Connection, club_id: int) -> str | None:
    found = conn.execute(text("SELECT code FROM national_team WHERE club_id = :c"),
                         {"c": club_id}).scalar()
    return str(found) if found is not None else None


def take_job(conn: Connection, world: World, meta: CareerMeta, code: str, day: date) -> int:
    """Make the user ``code``'s manager; its squad is picked for him if it has none. Returns the
    national team's club id."""
    club_id = conn.execute(text("SELECT club_id FROM national_team WHERE code = :c"),
                           {"c": code}).scalar()
    if club_id is None:
        raise JobRefused(f"no national team {code}")
    meta.user_nation_id = int(club_id)
    write_meta(conn, meta)
    ensure_squad(conn, world, meta, day)
    return int(club_id)


def leave_job(conn: Connection, meta: CareerMeta) -> None:
    meta.user_nation_id = None
    write_meta(conn, meta)


def ensure_squad(conn: Connection, world: World, meta: CareerMeta, day: date) -> None:
    """The user's national team's squad, picked for him when it's empty (at a call-up, or when
    he takes the job)."""
    if meta.user_nation_id is None:
        return
    has = conn.execute(text("SELECT 1 FROM national_squad WHERE club_id = :c LIMIT 1"),
                       {"c": meta.user_nation_id}).first()
    code = nation_code(conn, meta.user_nation_id)
    if has is None and code is not None:
        pick_squads(conn, world, meta, day, {code}, include_user=True)


def candidates(conn: Connection, world: World, meta: CareerMeta) -> list[Candidate]:
    """The players the user can call up, the best first."""
    assert meta.user_nation_id is not None
    code = nation_code(conn, meta.user_nation_id)
    assert code is not None
    chosen = {int(r[0]) for r in conn.execute(text(
        "SELECT player_id FROM national_squad WHERE club_id = :c"), {"c": meta.user_nation_id})}
    found = nation_candidates(conn, world, {code})[code]
    return [Candidate(pid, position, overall, pid in chosen)
            for pid, position, overall in sorted(found, key=lambda c: (-c[2], c[0]))]


def set_squad(conn: Connection, world: World, meta: CareerMeta, player_ids: list[int]) -> None:
    """The user's call-ups. The tactic's chosen line-up keeps only players still in it."""
    if meta.user_nation_id is None:
        raise JobRefused("you don't manage a national team")
    limit = squad_size(world)
    chosen = list(dict.fromkeys(player_ids))
    if not 11 <= len(chosen) <= limit:
        raise JobRefused(f"call up between 11 and {limit} players")
    eligible = {c.player_id for c in candidates(conn, world, meta)}
    if any(pid not in eligible for pid in chosen):
        raise JobRefused("a player not eligible for this country")
    club_id = meta.user_nation_id
    conn.execute(national_squad.delete().where(national_squad.c.club_id == club_id))
    conn.execute(national_squad.insert(), [{"club_id": club_id, "player_id": pid}
                                           for pid in chosen])
    lineup = conn.execute(text("SELECT lineup FROM tactic WHERE club_id = :c"),
                          {"c": club_id}).scalar()
    if lineup:
        kept = {k: v for k, v in json.loads(lineup).items() if int(v) in set(chosen)}
        conn.execute(text("UPDATE tactic SET lineup = :l WHERE club_id = :c"),
                     {"l": json.dumps(kept) if kept else None, "c": club_id})
