"""Intermediate records produced by source readers, before they become database rows."""

from dataclasses import dataclass, field
from datetime import date


@dataclass
class SourcePlayer:
    """A player read from a ratings source, with attributes in canonical names."""

    source: str
    source_id: str
    first_name: str
    last_name: str
    known_as: str | None
    birth_date: date
    nationality: str
    club: str
    league: str
    position: str
    alt_positions: list[str]
    preferred_foot: str
    weak_foot: int
    skill_moves: int
    height_cm: int | None
    weight_kg: int | None
    source_overall: int | None
    playstyles: list[str]
    attrs: dict[str, int] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return self.known_as or f"{self.first_name} {self.last_name}".strip()


@dataclass(frozen=True)
class TmPlayer:
    """A player from the transfermarkt-datasets snapshot (CC0)."""

    tm_id: int
    name: str
    first_name: str
    last_name: str
    birth_date: date
    citizenship: str | None
    height_cm: int | None
    foot: str | None
    position: str | None
    sub_position: str | None
    contract_expiry: date | None
    market_value_eur: int | None
    club_name: str | None
    city_of_birth: str | None
