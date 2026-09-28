"""The single active career of this local server (one player, one open save at a time)."""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Connection, Engine

from footsim.core.paths import REPO_ROOT, data_dir
from footsim.persistence.database import check_schema, open_database
from footsim.persistence.saves import SaveManager
from footsim.world.career import initialize_career
from footsim.world.context import get_world


class NoCareer(Exception):
    pass


class CareerSession:
    def __init__(self, saves_root: Path, base_world: Path) -> None:
        self.saves = SaveManager(saves_root)
        self.base_world = base_world
        self.slot: int | None = None
        self._engine: Engine | None = None
        # Writes (advance, play, tactics) are serialised; SQLite has one writer anyway.
        self.lock = threading.RLock()

    @property
    def active(self) -> bool:
        return self._engine is not None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            raise NoCareer("no career loaded")
        return self._engine

    def _open(self, slot: int, working: Path) -> None:
        self.close()
        engine = open_database(working)
        try:
            check_schema(engine)
        except Exception:
            engine.dispose()
            raise
        self._engine = engine
        self.slot = slot

    def new_career(self, slot: int, club_id: int, manager_name: str) -> None:
        with self.lock:
            self.close()
            working = self.saves.new_career(slot, self.base_world, overwrite=True)
            self._open(slot, working)
            with self.engine.begin() as conn:
                initialize_career(conn, get_world(), club_id, manager_name)
            self.saves.save(slot)

    def load(self, slot: int, autosave: bool = False) -> None:
        with self.lock:
            self.close()
            working = self.saves.load(slot, autosave=autosave)
            self._open(slot, working)

    def save(self) -> None:
        with self.lock:
            if self.slot is None:
                raise NoCareer("no career loaded")
            self.saves.save(self.slot)

    def autosave(self) -> None:
        with self.lock:
            if self.slot is not None:
                self.saves.autosave(self.slot)

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
        self._engine = None
        self.slot = None

    @contextmanager
    def read(self) -> Iterator[Connection]:
        with self.engine.connect() as conn:
            yield conn

    @contextmanager
    def write(self) -> Iterator[Connection]:
        with self.lock, self.engine.begin() as conn:
            yield conn


def default_session() -> CareerSession:
    return CareerSession(REPO_ROOT / "saves", data_dir() / "worlds" / "base-2026-27.sqlite")
