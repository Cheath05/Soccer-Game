"""Career-level state stored in game_meta."""

import json
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Connection, select, text

from footsim.persistence.schema import game_meta


@dataclass
class CareerMeta:
    world_seed: int
    current_date: date
    season_id: int
    base_calendar: str
    user_club_id: int | None
    manager_name: str | None
    # The user's board (W3-4): expectations, confidence and a budget from its plan. Off, the
    # user's club has none of them and its budget is its cash. Saves from before it have the
    # board.
    board_enabled: bool = True
    # The currency the user sees money in (finance.yaml currencies): server text and the prices
    # quoted to them use it. Saves from before it: dollars, the default.
    currency: str = "USD"

    @property
    def seed(self) -> int:
        return self.world_seed


def read_meta(conn: Connection) -> CareerMeta:
    values = {k: json.loads(v) for k, v in conn.execute(select(game_meta.c.key, game_meta.c.value))}
    return CareerMeta(
        world_seed=int(values["world_seed"]),
        current_date=date.fromisoformat(values["game_date"]),
        season_id=int(values.get("season_id", 1)),
        base_calendar=values.get("base_calendar", values.get("calendar", "")),
        user_club_id=values.get("user_club_id"),
        manager_name=values.get("manager_name"),
        board_enabled=bool(values.get("board_enabled", True)),
        currency=str(values.get("currency", "USD")),
    )


def write_meta(conn: Connection, meta: CareerMeta) -> None:
    values = {
        "world_seed": meta.world_seed,
        "game_date": meta.current_date.isoformat(),
        "season_id": meta.season_id,
        "base_calendar": meta.base_calendar,
        "user_club_id": meta.user_club_id,
        "manager_name": meta.manager_name,
        "board_enabled": meta.board_enabled,
        "currency": meta.currency,
    }
    for key, value in values.items():
        conn.execute(game_meta.delete().where(game_meta.c.key == key))
        conn.execute(game_meta.insert().values(key=key, value=json.dumps(value)))


# What the transfer market caches of every player (world/market.py: his attributes, position
# familiarities, value premium, reputation, birth date, and who is still playing) changes only
# through the writers that bump this counter: development, position training, retirement, the
# youth intake and the value premiums. The cache is keyed on it, so a cache filled before any of
# them ran, in this process or another (a sim worker, the game before a restart), is never used.
PLAYERS_EPOCH = "players_epoch"


def players_epoch(conn: Connection) -> int:
    """How many times the players' cached columns have changed in this save (0 before any)."""
    value = conn.execute(select(game_meta.c.value).where(
        game_meta.c.key == PLAYERS_EPOCH)).scalar_one_or_none()
    return int(json.loads(value)) if value is not None else 0


def bump_players_epoch(conn: Connection) -> None:
    """Record that the players' cached columns changed (in the writer's own transaction)."""
    conn.execute(text("INSERT INTO game_meta (key, value) VALUES (:k, '1') "
                      "ON CONFLICT(key) DO UPDATE SET value = CAST(value AS INTEGER) + 1"),
                 {"k": PLAYERS_EPOCH})
