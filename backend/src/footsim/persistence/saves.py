"""Career save slots (docs/adr/0001-sqlite-per-save.md).

Each slot directory holds:
  working.sqlite    the live game database while playing
  career.sqlite     the last manual save
  autosave.sqlite   the last autosave
  backups/          previous manual saves, newest kept
  slot.json         checksums and a summary for the load screen

Saves copy with SQLite's online backup API into a temp file, verify it with
``PRAGMA integrity_check``, fsync it, then atomically swap it in with ``os.replace``.
A crash mid-save therefore leaves the previous save intact.
"""

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

WORKING = "working.sqlite"
CAREER = "career.sqlite"
AUTOSAVE = "autosave.sqlite"
BACKUPS = "backups"
SLOT_INFO = "slot.json"


class SaveError(Exception):
    pass


@dataclass(frozen=True)
class SlotSummary:
    slot: int
    has_save: bool
    has_autosave: bool
    saved_at: str | None
    meta: dict[str, Any]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_database(src: Path, dst: Path) -> None:
    """Consistent copy of a (possibly open, WAL-mode) SQLite database."""
    dst.unlink(missing_ok=True)
    source = sqlite3.connect(src)
    target = sqlite3.connect(dst)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def _is_intact(path: Path) -> bool:
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return False
    return result is not None and result[0] == "ok"


def _fsync(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_game_meta(path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT key, value FROM game_meta").fetchall()
    finally:
        conn.close()
    return {key: json.loads(value) for key, value in rows}


class SaveManager:
    def __init__(self, root: Path, slots: int = 3, keep_backups: int = 5) -> None:
        self.root = root
        self.slots = slots
        self.keep_backups = keep_backups

    def slot_dir(self, slot: int) -> Path:
        if not 1 <= slot <= self.slots:
            raise SaveError(f"slot must be between 1 and {self.slots}, got {slot}")
        return self.root / f"slot_{slot}"

    def working_path(self, slot: int) -> Path:
        return self.slot_dir(slot) / WORKING

    def new_career(self, slot: int, base_world: Path, overwrite: bool = False) -> Path:
        """Start a career in ``slot`` from a built base world. Returns the working database."""
        directory = self.slot_dir(slot)
        if (directory / CAREER).exists() and not overwrite:
            raise SaveError(f"slot {slot} already has a career")
        directory.mkdir(parents=True, exist_ok=True)
        for name in (CAREER, AUTOSAVE, SLOT_INFO):
            (directory / name).unlink(missing_ok=True)
        _copy_database(base_world, directory / WORKING)
        return directory / WORKING

    def save(self, slot: int) -> None:
        self._write_snapshot(slot, CAREER, keep_backup=True)

    def autosave(self, slot: int) -> None:
        self._write_snapshot(slot, AUTOSAVE, keep_backup=False)

    def _write_snapshot(self, slot: int, name: str, keep_backup: bool) -> None:
        directory = self.slot_dir(slot)
        working = directory / WORKING
        if not working.exists():
            raise SaveError(f"slot {slot} has no game in progress")
        target = directory / name
        tmp = directory / f"{name}.tmp"
        _copy_database(working, tmp)
        if not _is_intact(tmp):
            tmp.unlink(missing_ok=True)
            raise SaveError("save failed its integrity check; previous save kept")
        _fsync(tmp)
        if keep_backup and target.exists():
            self._backup(directory, target)
        os.replace(tmp, target)
        self._record(directory, name, target)

    def _backup(self, directory: Path, current: Path) -> None:
        backups = directory / BACKUPS
        backups.mkdir(exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        os.replace(current, backups / f"career-{stamp}.sqlite")
        for old in sorted(backups.glob("career-*.sqlite"))[: -self.keep_backups]:
            old.unlink()

    def _record(self, directory: Path, name: str, target: Path) -> None:
        info_path = directory / SLOT_INFO
        info: dict[str, Any] = json.loads(info_path.read_text()) if info_path.exists() else {}
        info[name] = {
            "sha256": _sha256(target),
            "saved_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "meta": _read_game_meta(target),
        }
        tmp = info_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(info, indent=2))
        os.replace(tmp, info_path)

    def _valid(self, directory: Path, name: str) -> bool:
        path = directory / name
        if not path.exists() or not _is_intact(path):
            return False
        info_path = directory / SLOT_INFO
        if not info_path.exists():
            return False
        expected: str | None = json.loads(info_path.read_text()).get(name, {}).get("sha256")
        return expected == _sha256(path)

    def load(self, slot: int, autosave: bool = False) -> Path:
        """Restore a save into the working database. Falls back to the newest intact
        backup if the save is damaged. Returns the working database path."""
        directory = self.slot_dir(slot)
        name = AUTOSAVE if autosave else CAREER
        if self._valid(directory, name):
            source = directory / name
        else:
            source = self._newest_intact_backup(directory, slot)
        _copy_database(source, directory / WORKING)
        return directory / WORKING

    def _newest_intact_backup(self, directory: Path, slot: int) -> Path:
        for backup in sorted((directory / BACKUPS).glob("career-*.sqlite"), reverse=True):
            if _is_intact(backup):
                return backup
        raise SaveError(f"slot {slot}: no intact save or backup found")

    def list_slots(self) -> list[SlotSummary]:
        summaries = []
        for slot in range(1, self.slots + 1):
            directory = self.slot_dir(slot)
            info_path = directory / SLOT_INFO
            info: dict[str, Any] = json.loads(info_path.read_text()) if info_path.exists() else {}
            latest = info.get(CAREER) or info.get(AUTOSAVE) or {}
            summaries.append(
                SlotSummary(
                    slot=slot,
                    has_save=(directory / CAREER).exists(),
                    has_autosave=(directory / AUTOSAVE).exists(),
                    saved_at=latest.get("saved_at"),
                    meta=latest.get("meta", {}),
                )
            )
        return summaries
