import subprocess
from typing import Any

import pytest

from footsim.core import build_info as module
from footsim.core.build_info import build_info


@pytest.fixture(autouse=True)
def fresh_cache() -> Any:
    build_info.cache_clear()
    yield
    build_info.cache_clear()  # don't leave this test's answer for the next one


def test_without_git_the_environment_stands_in(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_git(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", no_git)
    monkeypatch.setenv("FOOTSIM_VERSION", "1.12")
    monkeypatch.setenv("FOOTSIM_COMMIT", "abc1234")
    monkeypatch.delenv("FOOTSIM_COMMIT_DATE", raising=False)
    monkeypatch.setenv("FOOTSIM_BRANCH", "main")
    assert build_info() == {"version": "1.12", "commit": "abc1234", "commit_date": "unknown",
                            "branch": "main", "dirty": False}
    build_info.cache_clear()
    monkeypatch.delenv("FOOTSIM_VERSION")
    assert build_info()["version"] == "unknown"


def test_a_git_that_hangs_or_fails_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def hangs(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired("git", 5)

    monkeypatch.setattr(subprocess, "run", hangs)
    monkeypatch.delenv("FOOTSIM_COMMIT", raising=False)
    assert build_info()["commit"] == "unknown"


def _git_says(monkeypatch: pytest.MonkeyPatch, described: str | None, commits: str | None
              ) -> None:
    """Pretend git answers `describe` with ``described`` and `rev-list --count` with ``commits``
    (None: it fails, as `describe` does with no tag)."""

    def fake(*args: str) -> str | None:
        return {"describe": described, "rev-list": commits}.get(args[0])

    monkeypatch.setattr(module, "_git", fake)


def test_the_version_is_the_tags_major_and_the_commits_since(
        monkeypatch: pytest.MonkeyPatch) -> None:
    _git_says(monkeypatch, "v1.0-12-gabc1234", "99")
    assert build_info()["version"] == "1.12"
    build_info.cache_clear()
    _git_says(monkeypatch, "v2.0-0-gabc1234", "99")  # on the tag itself
    assert build_info()["version"] == "2.0"
    build_info.cache_clear()
    _git_says(monkeypatch, "v10.0-103-g0123abc", "400")
    assert build_info()["version"] == "10.103"


def test_with_no_tag_the_version_counts_commits_from_zero(
        monkeypatch: pytest.MonkeyPatch) -> None:
    _git_says(monkeypatch, None, "47")
    assert build_info()["version"] == "0.47"


def test_the_answer_is_read_once(monkeypatch: pytest.MonkeyPatch) -> None:
    first = build_info()
    monkeypatch.setenv("FOOTSIM_COMMIT", "changed")
    assert build_info() is first
