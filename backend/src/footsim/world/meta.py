"""Career-level state stored in game_meta."""

import json
from dataclasses import dataclass, field
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
    # The leagues the user has switched off full simulation (world/fast_sim.py): their matches
    # get fast results. Empty, as in saves from before it: every league fully simulated.
    fast_leagues: list[str] = field(default_factory=list)
    # Bids and loan requests for the user's players while the game moves on (world/offers.py):
    # "stop" (Continue and Sim to stop for each, as before), "wait" (they wait on the Transfers
    # page without stopping), "auto" (answered by the rules below as they arrive).
    offer_mode: str = "stop"
    # "auto": a player without an asking price is sold for a bid of at least this percentage of
    # his value (countered at it below); None turns such bids down.
    offer_value_pct: int | None = None
    offer_loans: str = "reject"  # "auto": loan requests are "accept"ed or "reject"ed
    # The user's asking prices (EUR), by player: "auto" sells at or above it, counters below.
    asking_prices: dict[int, int] = field(default_factory=dict)
    # The national team the user manages (its club id; world/international), alongside the club
    # or on its own. None: none.
    user_nation_id: int | None = None
    # A college coach's game mode (W9d): "classic", or "builder" (programs have money and build
    # training facilities and stadiums, world/college/program.py). Saves from before it: classic.
    college_mode: str = "classic"
    # A college coach's OP players (world/college/god_player.py): player id -> the season he
    # was signed. One every few seasons; he never declares early, so he stays four years.
    god_players: dict[int, int] = field(default_factory=dict)

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
        fast_leagues=[str(k) for k in values.get("fast_leagues", [])],
        offer_mode=str(values.get("offer_mode", "stop")),
        offer_value_pct=values.get("offer_value_pct"),
        offer_loans=str(values.get("offer_loans", "reject")),
        asking_prices={int(k): int(v) for k, v in values.get("asking_prices", {}).items()},
        user_nation_id=values.get("user_nation_id"),
        college_mode=str(values.get("college_mode", "classic")),
        god_players={int(k): int(v) for k, v in values.get("god_players", {}).items()},
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
        "fast_leagues": meta.fast_leagues,
        "offer_mode": meta.offer_mode,
        "offer_value_pct": meta.offer_value_pct,
        "offer_loans": meta.offer_loans,
        "asking_prices": {str(k): v for k, v in meta.asking_prices.items()},
        "user_nation_id": meta.user_nation_id,
        "college_mode": meta.college_mode,
        "god_players": {str(k): v for k, v in meta.god_players.items()},
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
