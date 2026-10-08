"""Position training (data/config/rules/development.yaml, position_training).

The user can have one of their players learn a position: say an attacking midfielder who also
plays centrally, but not quite at his best there. Each month (on the 1st, with development)
his familiarity in it grows by ``rate_per_month``, faster when he's young, until he's natural in
it (``natural``). From then on he plays it at his full rating there (ratings/overall.py
familiarity bands: 18+ is natural). Fractions carry from month to month. It's the user's
choice for their own players; AI clubs pick formations that suit their players instead.
"""

from datetime import date

from sqlalchemy import Connection, text

from footsim.world.context import World
from footsim.world.meta import CareerMeta
from footsim.world.squads import display_name


class TrainingRefused(Exception):
    """Why a player can't train that position (shown to the user)."""


def _rate(world: World, age: float) -> float:
    rules = world.defs.development.position_training
    factor = rules.age_factor[-1][1]
    for limit, value in rules.age_factor:
        if age <= limit:
            factor = value
            break
    return rules.rate_per_month * factor


def familiarity(conn: Connection, player_id: int, position: str) -> int:
    value = conn.execute(text("SELECT familiarity FROM player_position WHERE player_id = :p AND "
                              "position = :pos"), {"p": player_id, "pos": position}).scalar()
    return int(value or 0)


def set_training(conn: Connection, world: World, meta: CareerMeta, player_id: int,
                 position: str | None, day: date) -> None:
    """Have one of the user's players learn ``position`` (None: stop training)."""
    owner = conn.execute(text("SELECT club_id FROM contract WHERE person_id = :p AND "
                              "is_active = 1 AND kind != 'loan'"), {"p": player_id}).scalar()
    if owner is None or owner != meta.user_club_id:
        raise TrainingRefused("Only your own players train with you.")
    conn.execute(text("DELETE FROM position_training WHERE player_id = :p"), {"p": player_id})
    if position is None:
        return
    if position not in world.defs.positions:
        raise TrainingRefused(f"Unknown position {position}.")
    if familiarity(conn, player_id, position) >= world.defs.development.position_training.natural:
        raise TrainingRefused("He's already natural there.")
    conn.execute(text("INSERT INTO position_training (player_id, position, progress, started) "
                      "VALUES (:p, :pos, 0, :d)"),
                 {"p": player_id, "pos": position, "d": day.isoformat()})


def train_positions(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """A month of position training. Returns news of players who became natural."""
    natural = world.defs.development.position_training.natural
    rows = conn.execute(text(
        "SELECT t.player_id, t.position, t.progress, pe.birth_date, pe.first_name, pe.last_name, "
        "pe.known_as, COALESCE(pp.familiarity, 0) AS familiarity, pp.player_id AS known "
        "FROM position_training t JOIN person pe ON pe.id = t.player_id "
        "LEFT JOIN player_position pp ON pp.player_id = t.player_id AND pp.position = t.position "
        "ORDER BY t.player_id")).all()
    news = []
    for r in rows:
        age = (day - date.fromisoformat(r.birth_date)).days / 365.25
        progress = float(r.progress) + _rate(world, age)
        points = int(progress)
        new = min(natural, int(r.familiarity) + points)
        if new != r.familiarity:
            if r.known is None:
                conn.execute(text("INSERT INTO player_position (player_id, position, familiarity) "
                                  "VALUES (:p, :pos, :f)"),
                             {"p": r.player_id, "pos": r.position, "f": new})
            else:
                conn.execute(text("UPDATE player_position SET familiarity = :f WHERE "
                                  "player_id = :p AND position = :pos"),
                             {"p": r.player_id, "pos": r.position, "f": new})
        if new >= natural:
            conn.execute(text("DELETE FROM position_training WHERE player_id = :p"),
                         {"p": r.player_id})
            news.append(f"{display_name(r.first_name, r.last_name, r.known_as)} is now natural "
                        f"at {world.defs.positions[r.position].name}.")
        else:
            conn.execute(text("UPDATE position_training SET progress = :g WHERE player_id = :p"),
                         {"g": progress - points, "p": r.player_id})
    return news


def training_of(conn: Connection, player_id: int) -> tuple[str, float] | None:
    """The position a player is learning, and the fraction toward his next point."""
    row = conn.execute(text("SELECT position, progress FROM position_training WHERE "
                            "player_id = :p"), {"p": player_id}).first()
    return (str(row.position), float(row.progress)) if row else None
