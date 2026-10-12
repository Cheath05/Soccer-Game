"""Heavy simulation in worker processes: Continue, Instant play and each step of sim to date.

Python runs one thread of Python at a time per process, so two players simulating in the
server itself would share one core. Here each heavy call runs in one of ``sim_workers``
processes (data/config/server.yaml), on the player's working copy of their career: the worker
opens the file, runs the call in one transaction and commits. Meanwhile the career's lock is
held in the server, exactly as an in-process write holds it, so nothing else writes to that
career until the worker is done; reads carry on (SQLite's WAL lets one process write while
others read). A career with ``sim_workers`` 0 (tests, the default for ``CareerSession``) runs
the call in the server instead. Either way it is the same code on the same database: the
result is identical.
"""

import multiprocessing
import threading
from collections.abc import Callable
from concurrent.futures import Future, ProcessPoolExecutor
from functools import partial
from pathlib import Path
from typing import Concatenate

from sqlalchemy import Connection, select

from footsim.api.session import CareerSession
from footsim.persistence.database import open_database
from footsim.persistence.schema import fixture
from footsim.world.career import play_user_instant
from footsim.world.context import World, get_world
from footsim.world.meta import read_meta

_pool: ProcessPoolExecutor | None = None
_pool_lock = threading.Lock()


def _warm() -> None:
    get_world()  # each worker loads the game's definitions once, when it starts


def _executor(workers: int) -> ProcessPoolExecutor:
    global _pool
    with _pool_lock:
        if _pool is None:
            # spawn: a fresh interpreter, never a fork of a server full of threads.
            _pool = ProcessPoolExecutor(max_workers=workers, initializer=_warm,
                                        mp_context=multiprocessing.get_context("spawn"))
        return _pool


def shutdown() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.shutdown(wait=True, cancel_futures=True)
            _pool = None


def _in_file[**P, R](path: str, job: Callable[Concatenate[Connection, World, P], R],
                     *args: P.args, **kwargs: P.kwargs) -> R:
    """In a worker: run ``job`` on the career file in one transaction."""
    engine = open_database(Path(path))
    try:
        with engine.begin() as conn:
            return job(conn, get_world(), *args, **kwargs)
    finally:
        engine.dispose()


def simulate[**P, R](session: CareerSession,
                     job: Callable[Concatenate[Connection, World, P], R],
                     *args: P.args, **kwargs: P.kwargs) -> R:
    """``job(conn, world, *args, **kwargs)`` as one write to the career: in a worker process
    when the career has ``sim_workers``, else here. ``job`` and its arguments go to another
    process, so ``job`` is a module-level function and the arguments plain values."""
    if session.sim_workers <= 0:
        with session.write() as conn:
            return job(conn, get_world(), *args, **kwargs)
    with session.lock:  # no other write to this career meanwhile, as in session.write()
        path = session.engine.url.database
        assert path is not None
        call: Callable[[], R] = partial(_in_file, path, job, *args, **kwargs)
        future: Future[R] = _executor(session.sim_workers).submit(call)
        return future.result()


def play_today(conn: Connection, world: World, fixture_id: int) -> None:
    """The user's match of today, played as Instant (for ``simulate``: takes plain values)."""
    meta = read_meta(conn)
    fx = conn.execute(select(fixture).where(fixture.c.id == fixture_id)).one()
    play_user_instant(conn, world, meta, fx, meta.current_date)
