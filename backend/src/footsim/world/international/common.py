"""What the rest of the game needs to know about national teams (W8): which clubs they are, and
which players are made-up home-based ones (kept out of the market, loans and transfers)."""

from sqlalchemy import Connection, text

from footsim.world.context import World

# The made-up home-based players: no club in the game, their nation's to call up (schema v26).
IN_POOL_SQL = "SELECT player_id FROM national_pool"
NATIONAL_CLUBS_SQL = "SELECT club_id FROM national_team"


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
