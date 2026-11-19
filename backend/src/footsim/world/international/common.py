"""What the rest of the game needs to know about national teams (W8): which clubs they are, and
which players are made-up home-based ones (kept out of the market, loans and transfers)."""

import json
from datetime import date

from sqlalchemy import Connection, text

from footsim.world.context import World

# The made-up home-based players: no club in the game, their nation's to call up (schema v26).
IN_POOL_SQL = "SELECT player_id FROM national_pool"
NATIONAL_CLUBS_SQL = "SELECT club_id FROM national_team"
TYPE = "international"  # competition.type of every national-team competition
# Competition types whose fixtures don't hold up a season's rollover (they run into July).
SUMMER_TYPES = (TYPE, "club_world_cup")
AWAY_KEY = "intl_away"  # game_meta: the window the called-up players are away for


def away_players(conn: Connection, day: date) -> set[int]:
    """The players away with their national teams on ``day`` (none outside a window)."""
    value = conn.execute(text("SELECT value FROM game_meta WHERE key = :k"),
                         {"k": AWAY_KEY}).scalar()
    window = json.loads(value) if value is not None else None
    if not isinstance(window, dict) or not (window["start"] <= day.isoformat() <= window["end"]):
        return set()
    return {int(r[0]) for r in conn.execute(text("SELECT player_id FROM national_squad"))}


def national_club_ids(conn: Connection) -> set[int]:
    return {int(r[0]) for r in conn.execute(text(NATIONAL_CLUBS_SQL))}


def is_national(conn: Connection, club_id: int) -> bool:
    return conn.execute(text("SELECT 1 FROM national_team WHERE club_id = :c"),
                        {"c": club_id}).first() is not None


def in_pool(conn: Connection, player_id: int) -> bool:
    return conn.execute(text("SELECT 1 FROM national_pool WHERE player_id = :p"),
                        {"p": player_id}).first() is not None


def nation_ids(conn: Connection, world: World) -> dict[str, set[int]]:
    """The save's nation rows that are each team's nationality, by FIFA code: every spelling
    the player data uses (teams.yaml ``names``)."""
    by_name = {str(r.name): int(r.id) for r in conn.execute(text("SELECT id, name FROM nation"))}
    return {code: {by_name[n] for n in team.nationalities if n in by_name}
            for code, team in world.defs.international.teams.items()}
