"""The patch notes under the version tag: data/changelog.yaml and GET /api/changelog."""

import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from footsim.accounts.store import AccountStore
from footsim.api import changelog
from footsim.api.app import create_app
from footsim.api.changelog import ChangelogError, load_changelog, version_key
from footsim.api.session import CareerSession, SessionRegistry
from footsim.core.build_info import build_info
from footsim.defs.loader import load_server

ENTRY = """\
- version: "1.2"
  date: "2026-10-07"
  title: "A title"
  changes:
    - "One thing"
"""


def _client(tmp_path: Path) -> TestClient:
    session = CareerSession(tmp_path / "saves", tmp_path / "world.sqlite")
    return TestClient(create_app(session, frontend=None))


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "changelog.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_changelog_file_loads_and_validates() -> None:
    entries = load_changelog()
    assert entries
    for entry in entries:
        assert entry.title and entry.changes
    assert entries[-1].version == "1.0"  # the history starts at the first numbered version


def test_versions_are_unique_and_newest_first() -> None:
    entries = load_changelog()
    keys = [version_key(entry.version) for entry in entries]
    assert len(set(keys)) == len(keys)
    assert keys == sorted(keys, reverse=True)
    # A later version can't be older: dates never go up the list.
    dates = [entry.date for entry in entries]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.parametrize("text", [
    ENTRY.replace('  title: "A title"\n', ""),                       # a field is missing
    ENTRY.replace('"1.2"', "1.2"),                                    # unquoted: a number, not text
    ENTRY.replace('"1.2"', '"v1.2"'),                                 # not MAJOR.MINOR
    ENTRY.replace('"1.2"', '"1.02"'),                                 # a leading zero
    ENTRY.replace('"1.2"', '"1"'),                                    # no minor
    ENTRY.replace('"2026-10-07"', '"7 October"'),                     # not a date
    ENTRY + "  extra: 1\n",                                           # a key that isn't one
    ENTRY.replace('  changes:\n    - "One thing"\n', "  changes: []\n"),    # nothing changed
    ENTRY.replace('"One thing"', '"  "'),                             # a blank bullet
    ENTRY + ENTRY,                                                    # the same version twice
    "version: 1.2\n",                                                 # not a list of entries
    "- version: [unclosed\n",                                         # not YAML at all
    "",                                                               # nothing in it
], ids=["no-title", "number", "v-prefix", "leading-zero", "no-minor", "bad-date", "extra-key",
        "no-changes", "blank-bullet", "duplicate", "not-a-list", "not-yaml", "empty"])
def test_a_malformed_file_is_an_error_not_a_blank(tmp_path: Path, text: str) -> None:
    with pytest.raises(ChangelogError):
        load_changelog(_write(tmp_path, text))


def test_a_missing_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ChangelogError):
        load_changelog(tmp_path / "nope.yaml")


def test_a_well_formed_file_loads(tmp_path: Path) -> None:
    [entry] = load_changelog(_write(tmp_path, ENTRY))
    assert (entry.version, entry.date, entry.title, entry.changes) == (
        "1.2", datetime.date(2026, 10, 7), "A title", ["One thing"])
    # YAML dates written without quotes are dates too.
    [entry] = load_changelog(_write(tmp_path, ENTRY.replace('"2026-10-07"', "2026-10-07")))
    assert entry.date == datetime.date(2026, 10, 7)


def test_the_endpoint_returns_the_entries_and_the_running_version(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/api/changelog")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == build_info()["version"]
    assert [e["version"] for e in body["entries"]] == [e.version for e in load_changelog()]
    first = body["entries"][0]
    assert set(first) == {"version", "date", "title", "changes"}
    datetime.date.fromisoformat(first["date"])  # a plain ISO date the page can show
    assert all(isinstance(bullet, str) for bullet in first["changes"])


def test_the_endpoint_puts_the_newest_first_whatever_the_file_order(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    newer = ENTRY.replace('"1.2"', '"1.10"')
    monkeypatch.setattr(changelog, "CHANGELOG", _write(tmp_path, ENTRY + newer))
    versions = [e["version"] for e in _client(tmp_path).get("/api/changelog").json()["entries"]]
    assert versions == ["1.10", "1.2"]  # numerically, not as text


def test_a_malformed_file_makes_the_endpoint_fail_loudly(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(changelog, "CHANGELOG", _write(tmp_path, ENTRY.replace('"1.2"', "1.2")))
    response = _client(tmp_path).get("/api/changelog")
    assert response.status_code == 500
    assert "malformed" in response.json()["detail"]


def test_the_changelog_is_behind_the_sign_in_when_accounts_are_on(tmp_path: Path) -> None:
    saves = tmp_path / "saves"
    accounts = AccountStore.in_saves(saves)
    accounts.add("Alex", "password1", owner=True, min_password_length=8)
    settings = load_server().model_copy(update={"failure_delay_seconds": 0.0, "sim_workers": 0})
    registry = SessionRegistry(saves, tmp_path / "world.sqlite", settings, accounts)
    client = TestClient(create_app(frontend=None, registry=registry))
    assert client.get("/api/changelog").status_code == 401
    assert client.post("/api/auth/login",
                       json={"name": "alex", "password": "password1"}).status_code == 200
    assert client.get("/api/changelog").status_code == 200
