"""Heavy simulation in worker processes (api/workers.py) gives exactly the career it gives in
the server, and two players' simulations run side by side. Needs the built world."""

import shutil
import sqlite3
import threading
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from footsim.api import workers
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir
from footsim.persistence.schema import club
from footsim.world.career import advance, sim_step
from footsim.world.meta import read_meta

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


@pytest.fixture(autouse=True)
def _pool() -> Iterator[None]:
    yield
    workers.shutdown()


def _career(root: Path, pick: int = 0) -> CareerSession:
    session = CareerSession(root, BASE_WORLD)
    with sqlite3.connect(BASE_WORLD) as conn:
        club_id = conn.execute("SELECT id FROM club ORDER BY id LIMIT 1 OFFSET ?",
                               (pick,)).fetchone()[0]
    session.new_career(1, club_id, "T")
    return session


def _twin(session: CareerSession, root: Path, sim_workers: int) -> CareerSession:
    shutil.copytree(session.saves.root / "slot_1", root / "slot_1")
    twin = CareerSession(root, BASE_WORLD)
    twin.load(1)
    twin.sim_workers = sim_workers
    return twin


def _dump(session: CareerSession) -> list[str]:
    path = session.engine.url.database
    assert path is not None
    with sqlite3.connect(path) as conn:
        return list(conn.iterdump())


def test_a_worker_gives_the_same_career(tmp_path: Path) -> None:
    original = _career(tmp_path / "a")
    here = _twin(original, tmp_path / "here", sim_workers=0)
    there = _twin(original, tmp_path / "there", sim_workers=2)
    assert _dump(here) == _dump(there)
    for session in (here, there):
        assert workers.simulate(session, advance).stop in ("match", "offer")
        with session.read() as conn:
            until = read_meta(conn).current_date + timedelta(days=30)
        steps = [workers.simulate(session, sim_step, until) for _ in range(3)]
        assert all(step.date for step in steps)
    assert _dump(here) == _dump(there)
    with there.read() as conn, original.read() as start:  # the server sees what was written
        assert read_meta(conn).current_date > read_meta(start).current_date


def test_two_players_simulate_side_by_side(tmp_path: Path) -> None:
    sessions = [_career(tmp_path / name, pick) for name, pick in (("a", 0), ("b", 5))]
    for session in sessions:
        session.sim_workers = 2
    results: dict[int, str] = {}

    def run(i: int) -> None:
        results[i] = workers.simulate(sessions[i], advance).stop

    threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=300)
    assert set(results) == {0, 1}
    assert set(results.values()) <= {"match", "offer"}
    for session in sessions:  # each still its own club
        with session.read() as conn:
            user = read_meta(conn).user_club_id
            assert conn.execute(select(club.c.id).where(club.c.id == user)).first()
