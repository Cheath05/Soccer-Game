"""The market's cache of every player's ratings (world/market.py) never changes a career.

Looking at the market fills the cache. On the 1st of a month the players develop before that
day's AI market runs, so a cache filled by a look at the market that morning must not be used
afterwards; nor may one filled before another process (a sim worker, or the game after a
restart) changed the ratings. Either way the career must be exactly the one it would have
been without the look. Needs the built world."""

import shutil
import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from footsim.api import workers
from footsim.api.app import create_app
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir
from footsim.world import market
from footsim.world.career import advance
from footsim.world.context import World, get_world
from footsim.world.meta import read_meta

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
DAYS = 3  # the 1st of the summer window (development, then the market) and two days more


@pytest.fixture(autouse=True)
def _fresh() -> Iterator[None]:
    market._CACHE.clear()
    yield
    workers.shutdown()
    market._CACHE.clear()


@pytest.fixture(scope="module")
def original(tmp_path_factory: pytest.TempPathFactory) -> CareerSession:
    session = CareerSession(Path(tmp_path_factory.mktemp("cache")) / "a", BASE_WORLD)
    with sqlite3.connect(BASE_WORLD) as conn:
        club_id = conn.execute("SELECT id FROM club ORDER BY id LIMIT 1").fetchone()[0]
    session.new_career(1, club_id, "T")
    with session.read() as conn:
        assert read_meta(conn).current_date == date(2026, 7, 1)  # the window's 1st
    return session


def _twin(session: CareerSession, root: Path) -> CareerSession:
    shutil.copytree(session.saves.root / "slot_1", root / "slot_1")
    twin = CareerSession(root, BASE_WORLD)
    twin.load(1)
    return twin


def _dump(session: CareerSession) -> list[str]:
    path = session.engine.url.database
    assert path is not None
    with sqlite3.connect(path) as conn:
        return list(conn.iterdump())


def _advance(session: CareerSession, days: int) -> None:
    workers.simulate(session, advance, max_days=days)


def _fill(conn: Connection, world: World) -> bool:
    """Fill the market's cache, as a day's market does."""
    meta = read_meta(conn)
    market._players(conn, world, meta, meta.current_date)
    return conn.engine in market._CACHE


def _look(session: CareerSession) -> None:
    response = TestClient(create_app(session=session, frontend=None)).get("/api/market/overview")
    assert response.status_code == 200


def _unwatched(original: CareerSession, root: Path, steps: list[int]) -> list[str]:
    """The career advanced by ``steps`` (each an ``advance``, which may stop early, at a bid),
    here, with no look at the market."""
    plain = _twin(original, root)
    for days in steps:
        _advance(plain, days)
    market._CACHE.clear()
    return _dump(plain)


def test_a_look_at_the_market_on_the_1st_changes_nothing(original: CareerSession,
                                                         tmp_path: Path) -> None:
    expected = _unwatched(original, tmp_path / "plain", [DAYS])
    viewed = _twin(original, tmp_path / "viewed")
    _look(viewed)  # 1 Jul, before the day's development
    _advance(viewed, DAYS)
    assert _dump(viewed) == expected


def test_a_look_before_another_process_advances_changes_nothing(original: CareerSession,
                                                                tmp_path: Path) -> None:
    """The look fills this process's cache; a fresh process (a sim worker, as after a restart)
    plays the 1st, developing the players; then this process plays on."""
    expected = _unwatched(original, tmp_path / "plain", [1, DAYS - 1])
    viewed = _twin(original, tmp_path / "viewed")
    _look(viewed)
    viewed.sim_workers = 1
    _advance(viewed, 1)  # in a new process
    viewed.sim_workers = 0
    _look(viewed)  # back here, on the 2nd
    _advance(viewed, DAYS - 1)
    assert _dump(viewed) == expected



# The epoch counts changes along one line of play, so it can't tell apart two lines of the same
# file (a save reloaded and played differently) or a rolled-back write. Each opening of a save
# is its own Engine, with its own cache; a failed write forgets its own.


def test_a_loaded_career_never_sees_the_cache_of_another(original: CareerSession,
                                                          tmp_path: Path) -> None:
    session = _twin(original, tmp_path / "t")
    _look(session)
    old = session.engine
    assert old in market._CACHE
    with session.read() as conn:  # a look begun before the load, on the old file
        session.load(1)  # the same working file, perhaps another line of play
        assert _fill(conn, get_world())
    assert session.engine is not old and session.engine not in market._CACHE


def test_a_failed_write_forgets_the_cache(original: CareerSession, tmp_path: Path) -> None:
    session = _twin(original, tmp_path / "t")
    with pytest.raises(RuntimeError), session.write() as conn:
        assert _fill(conn, get_world())
        raise RuntimeError("rolled back")
    assert session.engine not in market._CACHE
