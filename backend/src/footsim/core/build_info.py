"""Which build is running: the git commit the checkout is at, for the version tag in the game.

Read from git once, the first time it is asked for. The API asks when it starts, so a checkout
that moves on afterwards doesn't change what a running server reports. Where git isn't there
(a copy without .git), the FOOTSIM_COMMIT, FOOTSIM_COMMIT_DATE and FOOTSIM_BRANCH variables
stand in; anything still unknown is "unknown". It never raises.
"""

import os
import subprocess
from functools import cache

from footsim.core.paths import REPO_ROOT

UNKNOWN = "unknown"


def _git(*args: str) -> str | None:
    """What a git command prints in the repository, or None if git is missing or it fails."""
    try:
        done = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
                              errors="replace", timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _known(from_git: str | None, variable: str) -> str:
    return from_git or os.environ.get(variable) or UNKNOWN


@cache
def build_info() -> dict[str, str | bool]:
    """The commit (short hash), its date (ISO 8601), the branch, and whether tracked files have
    changed since the commit. Untracked files don't count as changes."""
    status = _git("status", "--porcelain", "--untracked-files=no")
    return {
        "commit": _known(_git("rev-parse", "--short", "HEAD"), "FOOTSIM_COMMIT"),
        "commit_date": _known(_git("log", "-1", "--format=%cI"), "FOOTSIM_COMMIT_DATE"),
        "branch": _known(_git("rev-parse", "--abbrev-ref", "HEAD"), "FOOTSIM_BRANCH"),
        "dirty": bool(status),
    }
