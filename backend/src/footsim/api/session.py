"""The careers open on this server: one ``CareerSession`` per account (one open save each),
held by the ``SessionRegistry``. Without accounts (FOOTSIM_AUTH unset) there is one player,
the owner, playing from the saves folder itself, as before accounts existed."""

import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine

from footsim.accounts.store import Account, AccountStore, saves_root
from footsim.core.paths import data_dir, saves_dir
from footsim.defs.loader import load_server
from footsim.defs.server import ServerDef
from footsim.persistence.database import check_schema, open_database
from footsim.persistence.migrations import migrate
from footsim.persistence.saves import SaveManager
from footsim.world.career import initialize_career
from footsim.world.context import get_world
from footsim.world.finance import set_sandbox_budget
from footsim.world.meta import read_meta
from footsim.world.money import set_currency


class NoCareer(Exception):
    pass


class CareerSession:
    def __init__(self, saves_root: Path, base_world: Path, keep_backups: int = 5) -> None:
        self.saves = SaveManager(saves_root, keep_backups=keep_backups)
        self.base_world = base_world
        self.slot: int | None = None
        self._engine: Engine | None = None
        # Writes (advance, play, tactics) are serialised; SQLite has one writer anyway.
        self.lock = threading.RLock()
        # Matches being watched, by fixture id. They belong to the career that was loaded
        # when they started: loading or starting a career discards them, and ``generation``
        # lets a match that finishes afterwards see it no longer belongs to this career.
        self.live_matches: dict[int, Any] = {}
        self.generation = 0
        self.sim: Any = None  # the latest sim-to-date job (api/sim.py), running or finished
        # Worker processes for heavy simulation (api/workers.py); 0 runs it in the server.
        self.sim_workers = 0

    @property
    def busy(self) -> bool:
        """A match is being watched or a sim-to-date is running."""
        return bool(self.live_matches) or bool(self.sim is not None and self.sim.running)

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
            migrate(engine)  # the working copy only; the save file changes on the next save
            check_schema(engine)
        except Exception:
            engine.dispose()
            raise
        self._engine = engine
        self.slot = slot

    def new_career(self, slot: int, club_id: int, manager_name: str,
                   budget_eur: int | None = None, board_enabled: bool = True,
                   currency: str = "USD") -> None:
        """Start a career. The sandbox: ``budget_eur`` is the club's budget to start with for
        fees and wages (the owner puts in the cash). ``board_enabled`` False plays without a
        board."""
        with self.lock:
            self.close()
            working = self.saves.new_career(slot, self.base_world, overwrite=True)
            self._open(slot, working)
            with self.engine.begin() as conn:
                initialize_career(conn, get_world(), club_id, manager_name,
                                  board_enabled=board_enabled)
                set_currency(conn, get_world(), currency)
                if budget_eur is not None:
                    set_sandbox_budget(conn, read_meta(conn), club_id, budget_eur * 100)
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
        self.live_matches.clear()
        self.sim = None
        self.generation += 1

    @contextmanager
    def read(self) -> Iterator[Connection]:
        with self.engine.connect() as conn:
            yield conn

    @contextmanager
    def write(self) -> Iterator[Connection]:
        with self.lock, self.engine.begin() as conn:
            yield conn


def default_session() -> CareerSession:
    return CareerSession(saves_dir(), default_base_world())


def default_base_world() -> Path:
    return data_dir() / "worlds" / "base-2026-27.sqlite"


LOCAL = Account(0, "local", is_owner=True, disabled=False)  # everyone, when accounts are off


class SessionRegistry:
    """Each account's open career. Without accounts (``accounts`` None) every request is the
    owner's. The world's definitions (``get_world``) are shared by everyone; careers aren't."""

    def __init__(self, saves: Path, base_world: Path, server: ServerDef,
                 accounts: AccountStore | None = None) -> None:
        self.saves_root = saves
        self.base_world = base_world
        self.server = server
        self.accounts = accounts
        self._sessions: dict[int, CareerSession] = {}
        self._used: dict[int, float] = {}
        self._lock = threading.Lock()

    @classmethod
    def single(cls, session: CareerSession, server: ServerDef | None = None) -> "SessionRegistry":
        """One career for everyone: the server without accounts, built around ``session``."""
        registry = cls(session.saves.root, session.base_world, server or load_server())
        registry._sessions[LOCAL.id] = session
        return registry

    def for_account(self, account: Account) -> CareerSession:
        now = time.monotonic()
        with self._lock:
            session = self._sessions.get(account.id)
            if session is None:
                keep = (self.server.owner_keep_backups if account.is_owner
                        else self.server.friend_keep_backups)
                session = CareerSession(saves_root(account, self.saves_root), self.base_world,
                                        keep_backups=keep)
                session.sim_workers = self.server.sim_workers
                self._sessions[account.id] = session
            self._used[account.id] = now
            self._rest_idle(now)
        return session

    def _rest_idle(self, now: float) -> None:
        """Let go of the database connections of careers nobody has used for a while. The
        career stays open: its next request simply opens a new connection."""
        idle = self.server.idle_close_minutes * 60
        for key, used in list(self._used.items()):
            session = self._sessions[key]
            if now - used > idle and not session.busy and session.active:
                session.engine.dispose()
                del self._used[key]

    def sessions(self) -> list[CareerSession]:
        with self._lock:
            return list(self._sessions.values())

    @property
    def in_use(self) -> bool:
        return any(session.busy for session in self.sessions())


def auth_enabled() -> bool:
    return os.environ.get("FOOTSIM_AUTH", "").strip().lower() in ("1", "true", "yes", "on")


def default_registry() -> SessionRegistry:
    """The server as configured: with accounts when FOOTSIM_AUTH is set, else one player."""
    root, server = saves_dir(), load_server()
    if not auth_enabled():
        session = CareerSession(root, default_base_world(),
                                keep_backups=server.owner_keep_backups)
        session.sim_workers = server.sim_workers
        return SessionRegistry.single(session, server)
    return SessionRegistry(root, default_base_world(), server, AccountStore.in_saves(root))
