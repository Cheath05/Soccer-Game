import subprocess
from typing import Any

import pytest

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
    monkeypatch.setenv("FOOTSIM_COMMIT", "abc1234")
    monkeypatch.delenv("FOOTSIM_COMMIT_DATE", raising=False)
    monkeypatch.setenv("FOOTSIM_BRANCH", "main")
    assert build_info() == {"commit": "abc1234", "commit_date": "unknown", "branch": "main",
                            "dirty": False}


def test_a_git_that_hangs_or_fails_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def hangs(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired("git", 5)

    monkeypatch.setattr(subprocess, "run", hangs)
    monkeypatch.delenv("FOOTSIM_COMMIT", raising=False)
    assert build_info()["commit"] == "unknown"


def test_the_answer_is_read_once(monkeypatch: pytest.MonkeyPatch) -> None:
    first = build_info()
    monkeypatch.setenv("FOOTSIM_COMMIT", "changed")
    assert build_info() is first
