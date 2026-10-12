"""Accounts (accounts/store.py, accounts/cli.py): passwords, sign-ins and where careers live."""

import io
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from footsim.accounts.store import (
    ACCOUNTS_FILE,
    AccountError,
    AccountStore,
    check_password,
    hash_password,
    saves_root,
    user,
)
from footsim.cli import main
from footsim.defs.loader import load_server

T0 = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path: Path) -> AccountStore:
    return AccountStore.in_saves(tmp_path)


def test_password_hash_round_trip() -> None:
    stored = hash_password("correct horse")
    assert stored.startswith("scrypt$") and "correct horse" not in stored
    assert check_password("correct horse", stored)
    assert not check_password("correct hors", stored)
    assert hash_password("correct horse") != stored  # salted
    assert not check_password("x", "garbage")


def test_add_verify_and_names(store: AccountStore) -> None:
    alex = store.add("Alex", "password1", owner=True, min_password_length=8)
    sam = store.add("sam", "password2", min_password_length=8)
    assert store.verify("alex", "password1") == alex  # names ignore case
    assert store.verify("Sam", "password1") is None
    assert store.verify("nobody", "password1") is None
    assert [a.name for a in store.accounts()] == ["Alex", "sam"]
    with pytest.raises(AccountError, match="already an account"):
        store.add("ALEX", "password3", min_password_length=8)
    with pytest.raises(AccountError, match="already an owner"):
        store.add("kim", "password3", owner=True, min_password_length=8)
    with pytest.raises(AccountError, match="at least 8"):
        store.add("kim", "short", min_password_length=8)
    for bad in ("", " ", "-dash", "a/b", "x" * 33):
        with pytest.raises(AccountError, match="a name is"):
            store.add(bad, "password3", min_password_length=8)
    assert not sam.is_owner


def test_sign_in_expires_and_is_extended_by_use(store: AccountStore) -> None:
    sam = store.add("sam", "password2", min_password_length=8)
    token = store.start_session(sam, days=30, now=T0)
    assert store.session_account(token, 30, now=T0) == sam
    assert store.session_account(token + "x", 30, now=T0) is None
    # Used on day 20, it now lasts until day 50.
    assert store.session_account(token, 30, now=T0 + timedelta(days=20)) == sam
    assert store.session_account(token, 30, now=T0 + timedelta(days=45)) == sam
    assert store.session_account(token, 30, now=T0 + timedelta(days=80)) is None
    store.end_session(token)
    assert store.session_account(token, 30, now=T0 + timedelta(days=46)) is None


def test_disable_and_new_password_sign_out_everywhere(store: AccountStore) -> None:
    sam = store.add("sam", "password2", min_password_length=8)
    token = store.start_session(sam, days=30, now=T0)
    store.set_password("sam", "password9", min_password_length=8)
    assert store.session_account(token, 30, now=T0) is None
    assert store.verify("sam", "password9") == sam
    token = store.start_session(sam, days=30, now=T0)
    store.set_disabled("sam", True)
    assert store.session_account(token, 30, now=T0) is None
    assert store.verify("sam", "password9") is None
    store.set_disabled("sam", False)
    assert store.verify("sam", "password9") is not None


def test_tokens_are_stored_only_as_hashes(store: AccountStore, tmp_path: Path) -> None:
    sam = store.add("sam", "password2", min_password_length=8)
    token = store.start_session(sam, days=30, now=T0)
    store.close()
    raw = (tmp_path / ACCOUNTS_FILE).read_bytes()
    assert token.encode() not in raw and b"password2" not in raw
    with sqlite3.connect(tmp_path / ACCOUNTS_FILE) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1


def test_owner_plays_from_the_saves_folder_itself(store: AccountStore, tmp_path: Path) -> None:
    owner = store.add("alex", "password1", owner=True, min_password_length=8)
    sam = store.add("sam", "password2", min_password_length=8)
    assert saves_root(owner, tmp_path) == tmp_path
    assert saves_root(sam, tmp_path) == tmp_path / "users" / sam.folder
    store.remove("sam")
    again = store.add("sam", "password2", min_password_length=8)
    assert again.id != sam.id and again.folder != sam.folder  # never inherits old careers


def test_only_one_owner_even_in_the_database(store: AccountStore) -> None:
    store.add("alex", "password1", owner=True, min_password_length=8)
    with pytest.raises(IntegrityError), store.engine.begin() as conn:
        conn.execute(user.insert().values(name="kim", name_key="kim", password_hash="x",
                                          is_owner=True, disabled=False, folder="f",
                                          created="2026-10-11"))


def test_long_and_unicode_passwords(store: AccountStore) -> None:
    with pytest.raises(AccountError, match="at most"):
        store.add("sam", "x" * 300, min_password_length=8)
    store.add("sam", "caf\u00e9-latte", min_password_length=8)
    assert store.verify("sam", "cafe\u0301-latte") is not None  # the same word, other form
    assert store.verify("sam", "y" * 5000) is None


def test_rename_keeps_careers_and_sign_ins(store: AccountStore) -> None:
    sam = store.add("sam", "password2", min_password_length=8)
    store.add("kim", "password3", min_password_length=8)
    token = store.start_session(sam, days=30, now=T0)
    renamed = store.rename("sam", "Samuel")
    assert (renamed.id, renamed.folder, renamed.name) == (sam.id, sam.folder, "Samuel")
    assert store.verify("samuel", "password2") is not None and store.find("sam") is None
    assert store.session_account(token, 30, now=T0) == renamed  # still signed in
    assert store.rename("samuel", "SAMUEL").name == "SAMUEL"  # just the case
    with pytest.raises(AccountError, match="already an account"):
        store.rename("samuel", "Kim")
    with pytest.raises(AccountError, match="a name is"):
        store.rename("samuel", "no/slashes")


def test_server_settings_load() -> None:
    server = load_server()
    assert server.session_days > 0 and server.min_password_length >= 8
    assert server.friend_keep_backups <= server.owner_keep_backups


def test_users_command(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                       monkeypatch: pytest.MonkeyPatch) -> None:
    saves = ["users", "--saves", str(tmp_path)]
    monkeypatch.setattr("sys.stdin", io.StringIO("password1\n"))
    assert main([*saves, "add", "Alex", "--owner", "--password-stdin"]) == 0
    assert main([*saves, "add", "sam", "--generate"]) == 0
    out = capsys.readouterr().out
    password = out.split("Password: ")[1].split()[0]
    store = AccountStore.in_saves(tmp_path)
    assert store.verify("alex", "password1") is not None
    assert store.verify("sam", password) is not None

    assert main([*saves, "list"]) == 0
    listing = capsys.readouterr().out
    assert "Alex" in listing and "owner" in listing and "sam" in listing

    assert main([*saves, "remove", "alex"]) == 1  # never the owner
    assert "can't be removed" in capsys.readouterr().err

    friend = tmp_path / "users" / store.get("sam").folder
    (friend / "slot_1").mkdir(parents=True)
    assert main([*saves, "remove", "sam"]) == 0
    assert friend.is_dir()  # careers kept unless asked
    assert main([*saves, "add", "kim", "--generate"]) == 0
    kim = tmp_path / "users" / store.get("kim").folder
    (kim / "slot_1").mkdir(parents=True)
    assert main([*saves, "remove", "kim", "--delete-saves"]) == 0
    assert not kim.exists() and (tmp_path / "users").is_dir()
    store.close()
