"""Position training (data/config/rules/development.yaml, position_training).

The user can have one of their players learn a position: say an attacking midfielder who also
plays centrally, but not quite at his best there. Each month (on the 1st, with development)
his familiarity in it grows by ``rate_per_month``, faster when he's young, until he's natural in
it (``natural``). From then on he plays it at his full rating there (ratings/overall.py
familiarity bands: 18+ is natural). Fractions carry from month to month. It's the user's
choice for their own players; AI clubs pick formations that suit their players instead.

With the assistant training positions (a setting, ``auto_train``), each month every one of the
user's players who isn't learning a position starts on his best alternate one: the position he
already plays a little (familiar but not natural) that he knows best. Once he's natural everywhere
he plays, he has nothing more to learn. A national team's manager (W8 I5) trains his squad's
players the same way (22 Nov), with a switch of their own; they learn at their clubs.
"""

from datetime import date

from sqlalchemy import Connection, text

from footsim.world.context import World
from footsim.world.meta import CareerMeta, bump_players_epoch
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


def _own_players_sql(club: bool, nation: bool) -> str | None:
    """SQL for the players the user trains: his club's (contracted, not on loan) and his national
    team's squad, as chosen; None for neither."""
    parts = []
    if club:
        parts.append("SELECT person_id AS pid FROM contract WHERE club_id = :club "
                     "AND is_active = 1 AND kind != 'loan'")
    if nation:
        parts.append("SELECT player_id AS pid FROM national_squad WHERE club_id = :nation")
    return " UNION ".join(parts) or None


def trains(conn: Connection, meta: CareerMeta, player_id: int) -> bool:
    """Whether the user trains the player: one of his club's, or in his national team's squad."""
    sql = _own_players_sql(meta.user_club_id is not None, meta.user_nation_id is not None)
    return sql is not None and conn.execute(
        text(f"SELECT 1 FROM ({sql}) WHERE pid = :p"),
        {"club": meta.user_club_id, "nation": meta.user_nation_id, "p": player_id}
    ).first() is not None


def set_training(conn: Connection, world: World, meta: CareerMeta, player_id: int,
                 position: str | None, day: date) -> None:
    """Have one of the user's players (his club's, or his national squad's) learn ``position``
    (None: stop training)."""
    if not trains(conn, meta, player_id):
        raise TrainingRefused("Only your own players train with you: your club's, or your "
                              "national team's squad.")
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


def auto_train(conn: Connection, world: World, meta: CareerMeta, day: date) -> int:
    """The assistant starts each of the user's players not learning a position on his best
    alternate one (the familiar but not natural position he knows best): his club's with
    ``auto_position_training``, his national squad's with ``auto_position_training_nation``.
    Returns how many."""
    sql = _own_players_sql(meta.auto_position_training and meta.user_club_id is not None,
                           meta.auto_position_training_nation
                           and meta.user_nation_id is not None)
    if sql is None:
        return 0
    natural = world.defs.development.position_training.natural
    rows = conn.execute(text(
        f"SELECT pp.player_id, pp.position, pp.familiarity FROM player_position pp "
        f"WHERE pp.player_id IN ({sql}) AND pp.familiarity > 0 AND pp.familiarity < :natural "
        f"AND pp.player_id NOT IN (SELECT player_id FROM position_training) "
        f"ORDER BY pp.player_id, pp.familiarity DESC, pp.position"),
        {"club": meta.user_club_id, "nation": meta.user_nation_id, "natural": natural}).all()
    chosen: dict[int, str] = {}
    for r in rows:
        if r.position in world.defs.positions:
            chosen.setdefault(int(r.player_id), str(r.position))
    if chosen:
        conn.execute(text("INSERT INTO position_training (player_id, position, progress, started) "
                          "VALUES (:p, :pos, 0, :d)"),
                     [{"p": pid, "pos": pos, "d": day.isoformat()}
                      for pid, pos in sorted(chosen.items())])
    return len(chosen)


def train_positions(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """A month of position training (the assistant's choices first, with the setting on).
    Returns news of players who became natural."""
    if meta.auto_position_training or meta.auto_position_training_nation:
        auto_train(conn, world, meta, day)
    natural = world.defs.development.position_training.natural
    rows = conn.execute(text(
        "SELECT t.player_id, t.position, t.progress, pe.birth_date, pe.first_name, pe.last_name, "
        "pe.known_as, COALESCE(pp.familiarity, 0) AS familiarity, pp.player_id AS known "
        "FROM position_training t JOIN person pe ON pe.id = t.player_id "
        "LEFT JOIN player_position pp ON pp.player_id = t.player_id AND pp.position = t.position "
        "ORDER BY t.player_id")).all()
    news = []
    changed = False
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
            changed = True
        if new >= natural:
            conn.execute(text("DELETE FROM position_training WHERE player_id = :p"),
                         {"p": r.player_id})
            news.append(f"{display_name(r.first_name, r.last_name, r.known_as)} is now natural "
                        f"at {world.defs.positions[r.position].name}.")
        else:
            conn.execute(text("UPDATE position_training SET progress = :g WHERE player_id = :p"),
                         {"g": progress - points, "p": r.player_id})
    if changed:
        bump_players_epoch(conn)
    return news


def training_of(conn: Connection, player_id: int) -> tuple[str, float] | None:
    """The position a player is learning, and the fraction toward his next point."""
    row = conn.execute(text("SELECT position, progress FROM position_training WHERE "
                            "player_id = :p"), {"p": player_id}).first()
    return (str(row.position), float(row.progress)) if row else None
