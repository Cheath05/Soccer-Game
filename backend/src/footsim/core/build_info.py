"""Which build is running: the version number and the git commit the checkout is at, for the
version tag in the game.

The version is MAJOR.MINOR. MAJOR is that of the latest git tag named like v1.0 (tags are always
vN.0, and the number goes up for a big change to the simulation) and MINOR the number of commits
since that tag, so it goes up with every update: v1.0 plus 12 commits is "1.12". With no tag, it
is "0." and the number of commits. The vite config (frontend/vite.config.ts) works it out the
same way for the page.

Read from git once, the first time it is asked for. The API asks when it starts, so a checkout
that moves on afterwards doesn't change what a running server reports. Where git isn't there
(a copy without .git), the FOOTSIM_VERSION, FOOTSIM_COMMIT, FOOTSIM_COMMIT_DATE and
FOOTSIM_BRANCH variables stand in; anything still unknown is "unknown". It never raises.
"""

import os
import re
import subprocess
from functools import cache

from footsim.core.paths import REPO_ROOT

UNKNOWN = "unknown"
# What `git describe --long` prints: tag, commits since it, commit ("v1.0-12-gabc1234").
_DESCRIBED = re.compile(r"^v(\d+)(?:\.\d+)*-(\d+)-g[0-9a-f]+$")


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


def _version() -> str:
    """MAJOR.MINOR from the latest v<major>.0 tag and the commits since it ("1.12"; "1.0" on the
    tag itself), or "0.<commits>" with no tag. Without git: FOOTSIM_VERSION, else "unknown"."""
    described = _git("describe", "--tags", "--match", "v[0-9]*", "--long")
    match = _DESCRIBED.match(described) if described else None
    if match:
        return f"{match[1]}.{match[2]}"
    commits = _git("rev-list", "--count", "HEAD")
    if commits and commits.isdigit():
        return f"0.{commits}"
    return os.environ.get("FOOTSIM_VERSION") or UNKNOWN


@cache
def build_info() -> dict[str, str | bool]:
    """The version (MAJOR.MINOR), the commit (short hash), its date (ISO 8601), the branch, and
    whether tracked files have changed since the commit. Untracked files don't count as changes."""
    status = _git("status", "--porcelain", "--untracked-files=no")
    return {
        "version": _version(),
        "commit": _known(_git("rev-parse", "--short", "HEAD"), "FOOTSIM_COMMIT"),
        "commit_date": _known(_git("log", "-1", "--format=%cI"), "FOOTSIM_COMMIT_DATE"),
        "branch": _known(_git("rev-parse", "--abbrev-ref", "HEAD"), "FOOTSIM_BRANCH"),
        "dirty": bool(status),
    }
