"""Career-level state stored in game_meta."""

import json
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Connection, select

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
