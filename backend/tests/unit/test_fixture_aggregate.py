"""The aggregate a second leg carries: both legs' goals for its home and away clubs."""

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Connection, create_engine, insert, select

from footsim.api.queries import _competitions, fixtures_out
from footsim.persistence.schema import competition, fixture, metadata

A, B, C, D = 1, 2, 3, 4
NAMES = {A: "Ajax", B: "Brugge", C: "Celtic", D: "Dundee"}


def _game(tie: str, leg: int | None, home: int, away: int, goals: tuple[int, int] | None,
          day: int, **extra: Any) -> dict[str, Any]:
    return {  # every row has the same keys, so the rows insert in one batch
        "extra_time": None, "home_pens": None, "away_pens": None,
        "season_id": 1, "competition_id": 1, "stage": "cup", "round": 3, "tie": tie, "leg": leg,
        "date": f"2026-10-{day:02d}", "home_club_id": home, "away_club_id": away,
        "status": "played" if goals else "scheduled",
        "home_goals": goals[0] if goals else None, "away_goals": goals[1] if goals else None,
        **extra,
    }


@pytest.fixture
def conn() -> Iterator[Connection]:
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(insert(competition).values(
            id=1, key="BELGIAN_CUP", name="Belgian Cup", short_name="Belgian Cup", type="cup",
            tier=1, sim_level="simulated"))
        connection.execute(insert(fixture), [
            # Tie 1: Ajax 2-1 Brugge, then Brugge 3-1 Ajax after extra time and a shoot-out.
            _game("1", 1, A, B, (2, 1), 1),
            _game("1", 2, B, A, (3, 1), 8, extra_time=1, home_pens=4, away_pens=5),
            # Tie 2: the first leg is played but the second is still to come.
            _game("2", 1, C, D, (0, 0), 1),
            _game("2", 2, D, C, None, 8),
            # Tie 3: a second leg with its first leg unplayed, and a single match.
            _game("3", 1, A, C, None, 2),
            _game("3", 2, C, A, (1, 1), 9),
            _game("4", None, A, D, (5, 0), 3),
        ])
        yield connection
    engine.dispose()


def _out(conn: Connection, where: Any = None) -> dict[tuple[str | None, int | None], Any]:
    query = select(fixture)
    if where is not None:
        query = query.where(where)
    rows = conn.execute(query).all()
    return {(f.tie, f.leg): f for f in fixtures_out(conn, rows, NAMES, _competitions(conn))}


def test_a_played_second_leg_carries_the_aggregate_from_its_own_point_of_view(
        conn: Connection) -> None:
    second = _out(conn)[("1", 2)]
    # Brugge (home) 1 + 3, Ajax (away) 2 + 1; the penalties are not goals.
    assert (second.agg_home, second.agg_away) == (4, 3)
    assert (second.leg1_home, second.leg1_away) == (1, 2)
    assert (second.home_pens, second.away_pens) == (4, 5)


def test_the_first_leg_comes_from_one_query_when_it_is_not_in_the_list(conn: Connection) -> None:
    second = _out(conn, fixture.c.leg == 2)[("1", 2)]
    assert (second.agg_home, second.agg_away) == (4, 3)


def test_a_second_leg_still_to_play_has_the_first_leg_but_no_aggregate(conn: Connection) -> None:
    second = _out(conn)[("2", 2)]
    assert (second.agg_home, second.agg_away) == (None, None)
    assert (second.leg1_home, second.leg1_away) == (0, 0)


def test_no_aggregate_without_a_played_first_leg_or_on_other_fixtures(conn: Connection) -> None:
    games = _out(conn)
    for key in (("3", 2), ("1", 1), ("2", 1), ("4", None)):
        game = games[key]
        assert (game.agg_home, game.agg_away, game.leg1_home, game.leg1_away) == (
            None, None, None, None), key
