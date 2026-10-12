"""Who may play on this server, and who is signed in where.

The accounts live in ``accounts.sqlite`` at the top of the saves folder, apart from every
career. Passwords are kept only as scrypt hashes, and a sign-in is a random token the browser
holds in a cookie, of which only the SHA-256 is stored, so a copy of this file signs no one in.

The owner (the person running the server) plays from the saves folder itself, so careers made
before there were accounts stay where they are; everyone else gets ``users/<folder>/`` inside
it, a random name made with the account, so a new account can never inherit an old one's.
"""

import base64
import hashlib
import hmac
import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    Engine,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Row,
    String,
    Table,
    func,
    select,
    text,
)

from footsim.persistence.database import open_database

ACCOUNTS_FILE = "accounts.sqlite"
ACCOUNTS_VERSION = 1  # PRAGMA user_version; bump with a step in _migrate
USERS_DIR = "users"
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,31}$")

# scrypt at n=2^14, r=8: 16 MB and roughly 50 ms per hash, the interactive-login setting.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _SCRYPT_LEN = 2**14, 8, 1, 32
_REFRESH_AFTER = timedelta(hours=1)  # a sign-in in use is extended at most this often

metadata = MetaData()

user = Table(
    "user", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String, nullable=False),
    Column("name_key", String, nullable=False, unique=True),  # lower-cased: names are unique
    Column("password_hash", String, nullable=False),
    Column("is_owner", Boolean, nullable=False, default=False),
    Column("disabled", Boolean, nullable=False, default=False),
    Column("folder", String, nullable=False, unique=True),  # users/<folder>, never reused
    Column("created", String, nullable=False),
    Index("one_owner", "is_owner", unique=True, sqlite_where=text("is_owner")),
    sqlite_autoincrement=True,
)

login_session = Table(
    "login_session", metadata,
    Column("token_hash", String, primary_key=True),
    Column("user_id", Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
    Column("created", String, nullable=False),
    Column("last_seen", String, nullable=False),
    Column("expires", String, nullable=False),
)


class AccountError(Exception):
    """A request the accounts can't carry out; the message says why, for the person."""


@dataclass(frozen=True)
class Account:
    id: int
    name: str
    is_owner: bool
    disabled: bool
    folder: str = ""


MAX_PASSWORD = 256


def _bytes(password: str) -> bytes:
    # The same password typed on a phone and a computer can differ in Unicode form.
    return unicodedata.normalize("NFKC", password).encode()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(_bytes(password), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R,
                            p=_SCRYPT_P, dklen=_SCRYPT_LEN)
    b64 = base64.b64encode
    return (f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}$"
            f"{b64(salt).decode()}${b64(digest).decode()}")


def check_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        if len(password) > MAX_PASSWORD:
            return False
        expected = base64.b64decode(digest)
        got = hashlib.scrypt(_bytes(password), salt=base64.b64decode(salt), n=int(n),
                             r=int(r), p=int(p), dklen=len(expected))
    except ValueError:
        return False
    return hmac.compare_digest(got, expected)


@cache
def _dummy_hash() -> str:
    """Checked when a name is unknown, so that costs what a wrong password does."""
    return hash_password(secrets.token_urlsafe(16))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def _now() -> datetime:
    return datetime.now(UTC)


def saves_root(account: Account, root: Path) -> Path:
    """Where this account's save slots live: the saves folder itself for the owner, so the
    careers from before accounts stay put; ``users/<id>`` inside it for everyone else."""
    return root if account.is_owner else root / USERS_DIR / account.folder


class AccountStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.engine: Engine = open_database(path)
        self._migrate()

    @classmethod
    def in_saves(cls, saves: Path) -> "AccountStore":
        return cls(saves / ACCOUNTS_FILE)

    def close(self) -> None:
        self.engine.dispose()

    def _migrate(self) -> None:
        with self.engine.begin() as conn:
            version: int = conn.execute(text("PRAGMA user_version")).scalar_one()
            if version > ACCOUNTS_VERSION:
                raise AccountError(f"{self.path} is from a newer footsim (accounts "
                                   f"v{version}, this build reads v{ACCOUNTS_VERSION})")
            if version == 0:
                metadata.create_all(conn)
                conn.execute(text(f"PRAGMA user_version = {ACCOUNTS_VERSION}"))

    # --- accounts -------------------------------------------------------------------------

    @staticmethod
    def _account(row: Row[Any]) -> Account:
        return Account(row.id, row.name, bool(row.is_owner), bool(row.disabled), row.folder)

    def accounts(self) -> list[Account]:
        with self.engine.connect() as conn:
            return [self._account(r) for r in conn.execute(select(user).order_by(user.c.id))]

    def find(self, name: str) -> Account | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(user).where(user.c.name_key == name.strip().lower())).first()
        return self._account(row) if row is not None else None

    def get(self, name: str) -> Account:
        account = self.find(name)
        if account is None:
            raise AccountError(f"no account called {name!r}")
        return account

    def add(self, name: str, password: str, *, min_password_length: int, owner: bool = False,
            now: datetime | None = None) -> Account:
        name = _check_name(name)
        _check_new_password(password, min_password_length)
        with self.engine.begin() as conn:
            if conn.execute(select(user.c.id).where(user.c.name_key == name.lower())).first():
                raise AccountError(f"there is already an account called {name!r}")
            if owner and conn.execute(select(user.c.id).where(user.c.is_owner)).first():
                raise AccountError("there is already an owner: the owner plays from the saves "
                                   "folder itself, so there can only be one")
            folder = secrets.token_hex(8)
            new_id = conn.execute(user.insert().values(
                name=name, name_key=name.lower(), password_hash=hash_password(password),
                is_owner=owner, disabled=False, folder=folder,
                created=_stamp(now or _now()))).inserted_primary_key
        assert new_id is not None
        return Account(int(new_id[0]), name, owner, False, folder)

    def set_password(self, name: str, password: str, *, min_password_length: int) -> None:
        """A new password signs the account out everywhere."""
        _check_new_password(password, min_password_length)
        account = self.get(name)
        with self.engine.begin() as conn:
            conn.execute(user.update().where(user.c.id == account.id)
                         .values(password_hash=hash_password(password)))
            conn.execute(login_session.delete().where(login_session.c.user_id == account.id))

    def rename(self, name: str, new_name: str) -> Account:
        """A new name to sign in with. Their careers and sign-ins stay as they are (the folder
        and the sign-ins belong to the account, not its name)."""
        account = self.get(name)
        new_name = _check_name(new_name)
        with self.engine.begin() as conn:
            taken = conn.execute(select(user.c.id).where(user.c.name_key == new_name.lower(),
                                                         user.c.id != account.id)).first()
            if taken:
                raise AccountError(f"there is already an account called {new_name!r}")
            conn.execute(user.update().where(user.c.id == account.id)
                         .values(name=new_name, name_key=new_name.lower()))
        return self.get(new_name)

    def set_disabled(self, name: str, disabled: bool) -> None:
        account = self.get(name)
        with self.engine.begin() as conn:
            conn.execute(user.update().where(user.c.id == account.id).values(disabled=disabled))
            if disabled:
                conn.execute(login_session.delete()
                             .where(login_session.c.user_id == account.id))

    def remove(self, name: str) -> Account:
        """Delete the account and its sign-ins (not its saves: the caller decides that)."""
        account = self.get(name)
        with self.engine.begin() as conn:
            conn.execute(login_session.delete().where(login_session.c.user_id == account.id))
            conn.execute(user.delete().where(user.c.id == account.id))
        return account

    def verify(self, name: str, password: str) -> Account | None:
        """The account if the name and password match and it isn't disabled. An unknown name
        costs the same hash as a wrong password, so timing doesn't reveal which names exist."""
        with self.engine.connect() as conn:
            row = conn.execute(select(user).where(user.c.name_key == name.strip().lower())).first()
        if row is None:
            check_password(password, _dummy_hash())
            return None
        if not check_password(password, row.password_hash) or row.disabled:
            return None
        return self._account(row)

    # --- sign-ins -------------------------------------------------------------------------

    def start_session(self, account: Account, days: int, now: datetime | None = None) -> str:
        now = now or _now()
        token = secrets.token_urlsafe(32)
        with self.engine.begin() as conn:
            conn.execute(login_session.delete().where(login_session.c.expires < _stamp(now)))
            conn.execute(login_session.insert().values(
                token_hash=_token_hash(token), user_id=account.id, created=_stamp(now),
                last_seen=_stamp(now), expires=_stamp(now + timedelta(days=days))))
        return token

    def session_account(self, token: str, days: int, now: datetime | None = None) -> Account | None:
        """Who a sign-in token belongs to, or None when it's unknown, expired or the account
        is disabled. A sign-in in use is extended to ``days`` from now."""
        now = now or _now()
        key = _token_hash(token)
        with self.engine.connect() as conn:
            row = conn.execute(
                select(login_session.c.last_seen, login_session.c.expires, user)
                .join(user, user.c.id == login_session.c.user_id)
                .where(login_session.c.token_hash == key)).first()
        if row is None or row.disabled or row.expires <= _stamp(now):
            return None
        if datetime.fromisoformat(row.last_seen) + _REFRESH_AFTER <= now:
            with self.engine.begin() as conn:
                conn.execute(login_session.update().where(login_session.c.token_hash == key)
                             .values(last_seen=_stamp(now),
                                     expires=_stamp(now + timedelta(days=days))))
        return self._account(row)

    def end_session(self, token: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(login_session.delete()
                         .where(login_session.c.token_hash == _token_hash(token)))

    def session_count(self, account: Account) -> int:
        with self.engine.connect() as conn:
            return int(conn.execute(select(func.count()).select_from(login_session).where(
                login_session.c.user_id == account.id,
                login_session.c.expires > _stamp(_now()))).scalar_one())


def _check_name(name: str) -> str:
    name = name.strip()
    if not NAME_PATTERN.match(name):
        raise AccountError("a name is 1-32 letters, digits, spaces, dots, dashes or "
                           "underscores, starting with a letter or digit")
    return name


def _check_new_password(password: str, min_length: int) -> None:
    if len(password) < min_length:
        raise AccountError(f"a password needs at least {min_length} characters")
    if len(password) > MAX_PASSWORD:
        raise AccountError(f"a password can have at most {MAX_PASSWORD} characters")
    if password != password.strip():
        raise AccountError("a password can't start or end with a space")
