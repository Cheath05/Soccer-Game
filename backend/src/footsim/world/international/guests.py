"""The Club World Cup's guest clubs (W10): real clubs of the regions the game has no league for
(Africa, most of Asia, Oceania), from data/config/international/club_world_cup.yaml.

A guest is a club row of its country, with no league, no finances and no contracts. Its squad is
made-up players of its country, rated so its line-up plays at the guest's level, made the way a
national team's home-based players are (world/international/pools.py), and they are that country's
home-based players too (``national_pool``): Al Ahly's are Egypt's to call up. They stay out of the
market. A guest's squad is topped up before each Club World Cup (C2).
"""

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import Connection, text

from footsim.core.rng import derive_rng
from footsim.importers.generate import club_reputation
from footsim.persistence.schema import (
    club,
    guest_club,
    guest_player,
    national_pool,
    person,
    player,
    player_attr,
    player_personality,
    player_position,
    player_state,
)
from footsim.world.context import World
from footsim.world.international.common import nation_ids
from footsim.world.international.pools import _make, _names
from footsim.world.meta import CareerMeta, bump_players_epoch

GUEST_CLUBS_SQL = "SELECT club_id FROM guest_club"


def guest_club_ids(conn: Connection) -> set[int]:
    return {int(r[0]) for r in conn.execute(text(GUEST_CLUBS_SQL))}


def ensure_guests(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """Every guest club and its squad, if the save hasn't got them (after the national teams,
    whose nation rows they use). Returns news (none)."""
    if conn.execute(text("SELECT 1 FROM guest_club LIMIT 1")).first() is not None:
        return []
    spec = world.defs.international
    rules = spec.rules
    ids = nation_ids(conn, world)
    names = _names(conn, world, ids)
    build = world.defs.world_build
    next_id = int(conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM person")).scalar_one()) + 1
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for guest in spec.club_world_cup.guests:
        nation_id = min(ids[guest.country]) if ids.get(guest.country) else None
        reputation = club_reputation([guest.level] * 16, build.reputation)
        club_id = int(conn.execute(club.insert().values(
            name=guest.name, nation_id=nation_id, source_league=None, reputation=reputation,
            stadium_name=guest.stadium, stadium_capacity=guest.capacity)).lastrowid)
        conn.execute(guest_club.insert().values(club_id=club_id,
                                                confederation=guest.confederation,
                                                level=guest.level))
        rng = derive_rng(meta.seed, "guest-club", guest.name)
        first, last = names[guest.country]
        for position, (starters, reserves) in sorted(rules.places.items()):
            for k in range(starters + reserves):
                want = guest.level - (0.0 if k < starters else rules.depth_drop)
                pid = next_id
                next_id += 1
                _make(rows, world, rng, pid, guest.country, nation_id, position,
                      want + float(rng.normal(0, rules.quality_sd)), day,
                      str(rng.choice(first)), str(rng.choice(last)), reputation)
                rows["guest"].append({"player_id": pid, "club_id": club_id})
    for table, key in ((person, "person"), (player, "player"), (player_attr, "attr"),
                       (player_position, "position"), (player_personality, "personality"),
                       (player_state, "state"), (national_pool, "pool"), (guest_player, "guest")):
        if rows[key]:
            conn.execute(table.insert(), rows[key])
    if rows["player"]:
        bump_players_epoch(conn)
    return []
