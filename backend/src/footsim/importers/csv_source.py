"""Reads a ratings CSV through an import profile."""

import csv
from datetime import date
from pathlib import Path

from footsim.importers.profile import ImportProfile
from footsim.importers.records import SourcePlayer


class SourceFormatError(Exception):
    """The source file doesn't match its import profile."""


def _int_or_none(value: str | None) -> int | None:
    value = (value or "").strip()
    return int(float(value)) if value else None


def read_players(path: Path, profile: ImportProfile) -> list[SourcePlayer]:
    cols = profile.columns
    players: list[SourcePlayer] = []
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        needed = [*cols.values(), *profile.attributes.values(), *profile.filters]
        missing = [c for c in needed if c not in (reader.fieldnames or [])]
        if missing:
            raise SourceFormatError(f"{path.name} lacks columns {missing}")
        for line, row in enumerate(reader, start=2):
            if any(row[col] != value for col, value in profile.filters.items()):
                continue
            try:
                players.append(_parse_row(row, profile))
            except (KeyError, ValueError) as exc:
                raise SourceFormatError(f"{path.name} line {line}: {exc}") from exc
    return players


def _get(row: dict[str, str], profile: ImportProfile, field: str) -> str:
    column = profile.columns.get(field)
    return (row.get(column) or "").strip() if column else ""


def _position(code: str, profile: ImportProfile) -> str:
    if code not in profile.positions:
        raise ValueError(f"unmapped position {code!r}")
    return profile.positions[code]


def _parse_row(row: dict[str, str], profile: ImportProfile) -> SourcePlayer:
    position = _position(_get(row, profile, "position"), profile)
    alt_codes = _get(row, profile, "alt_positions").split()
    alt_positions: list[str] = []
    for code in alt_codes:
        mapped = _position(code, profile)
        if mapped != position and mapped not in alt_positions:
            alt_positions.append(mapped)
    playstyles = [p.strip() for p in _get(row, profile, "playstyles").split(",") if p.strip()]
    attrs = {attr: int(row[column]) for attr, column in profile.attributes.items()}
    return SourcePlayer(
        source=profile.source,
        source_id=_get(row, profile, "source_id"),
        first_name=_get(row, profile, "first_name"),
        last_name=_get(row, profile, "last_name"),
        known_as=_get(row, profile, "known_as") or None,
        birth_date=date.fromisoformat(_get(row, profile, "birth_date")),
        nationality=_get(row, profile, "nationality"),
        club=_get(row, profile, "club"),
        league=_get(row, profile, "league"),
        position=position,
        alt_positions=alt_positions,
        preferred_foot=(_get(row, profile, "preferred_foot") or "Right").lower(),
        weak_foot=_int_or_none(_get(row, profile, "weak_foot")) or 2,
        skill_moves=_int_or_none(_get(row, profile, "skill_moves")) or 2,
        height_cm=_int_or_none(_get(row, profile, "height_cm")),
        weight_kg=_int_or_none(_get(row, profile, "weight_kg")),
        source_overall=_int_or_none(_get(row, profile, "overall")),
        playstyles=playstyles,
        attrs=attrs,
    )
