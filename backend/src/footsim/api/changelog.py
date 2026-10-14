"""The patch notes under the version tag: ``data/changelog.yaml``, served newest first.

Each entry says which version it shipped in (MAJOR.MINOR, as ``core/build_info.py`` works it
out) and what a player would notice. The file is checked whenever it is read: a malformed one
is an error (the endpoint answers 500 and the tests fail), never a quietly empty list.
"""

import datetime
from pathlib import Path
from typing import Annotated

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, ValidationError

from footsim.core.build_info import build_info
from footsim.core.paths import REPO_ROOT

CHANGELOG = REPO_ROOT / "data" / "changelog.yaml"

router = APIRouter(prefix="/api")

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ChangelogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a misspelt key is an error, not a lost bullet

    # "1.53": MAJOR.MINOR as whole numbers without leading zeros, so no two spellings of one version
    version: Annotated[str, StringConstraints(pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)$")]
    date: datetime.date
    title: Text
    changes: Annotated[list[Text], Field(min_length=1)]


class Changelog(BaseModel):
    version: str  # the version this server runs ("unknown" where git isn't available)
    entries: list[ChangelogEntry]  # newest first


_ENTRIES = TypeAdapter(list[ChangelogEntry])


class ChangelogError(Exception):
    """The changelog file is missing or malformed."""


def version_key(version: str) -> tuple[int, int]:
    major, minor = version.split(".")
    return int(major), int(minor)


def load_changelog(path: Path | None = None) -> list[ChangelogEntry]:
    """The entries of ``path`` (default: the changelog in the repository), validated: every
    field present and well formed, each version once. Raises ChangelogError otherwise."""
    path = path or CHANGELOG
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ChangelogError(f"{path.name} can't be read: {exc}") from exc
    try:
        entries = _ENTRIES.validate_python(raw)
    except ValidationError as exc:
        raise ChangelogError(f"{path.name} is malformed: {exc}") from exc
    seen: set[str] = set()
    for entry in entries:
        if entry.version in seen:
            raise ChangelogError(f"{path.name}: version {entry.version} appears twice")
        seen.add(entry.version)
    return entries


@router.get("/changelog")
def get_changelog() -> Changelog:
    """The patch notes, newest first, and the version this server is running (so the page can
    mark where the player is). Behind the sign-in with the rest of /api when accounts are on."""
    try:
        entries = load_changelog()
    except ChangelogError as exc:
        raise HTTPException(500, str(exc)) from exc
    entries.sort(key=lambda entry: version_key(entry.version), reverse=True)
    return Changelog(version=str(build_info()["version"]), entries=entries)
