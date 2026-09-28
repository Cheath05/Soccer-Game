"""Import profiles (data/import_profiles/*.yaml): how a source file maps onto our model."""

from pathlib import Path

import yaml
from pydantic import Field, model_validator

from footsim.defs.common import DefModel
from footsim.domain.attributes import ATTRIBUTES

REQUIRED_COLUMNS = (
    "source_id",
    "first_name",
    "last_name",
    "birth_date",
    "nationality",
    "club",
    "league",
    "position",
)
OPTIONAL_COLUMNS = (
    "known_as",
    "alt_positions",
    "preferred_foot",
    "weak_foot",
    "skill_moves",
    "height_cm",
    "weight_kg",
    "overall",
    "playstyles",
)


class DerivedTerm(DefModel):
    attr: str | None = None
    max_of: list[str] = Field(default=[], alias="max")
    w: float = Field(gt=0)

    @model_validator(mode="after")
    def _one_source(self) -> "DerivedTerm":
        if (self.attr is None) == (not self.max_of):
            raise ValueError("a term needs exactly one of 'attr' or 'max'")
        for name in [self.attr, *self.max_of]:
            if name is not None and name not in ATTRIBUTES:
                raise ValueError(f"unknown attribute {name!r}")
        return self

    def inputs(self) -> list[str]:
        return [self.attr] if self.attr else list(self.max_of)


class DerivedAttribute(DefModel):
    terms: list[DerivedTerm]
    noise_sd: float = Field(default=0.0, ge=0.0)
    goalkeepers_only: bool = False


class ImportProfile(DefModel):
    key: str
    source: str
    description: str = ""
    filters: dict[str, str] = {}
    columns: dict[str, str]
    attributes: dict[str, str]
    positions: dict[str, str]
    leagues: dict[str, str] = {}
    league_nations: dict[str, str] = {}
    derived: dict[str, DerivedAttribute] = {}
    plus_multiplier: float = 1.6
    playstyle_effects: dict[str, dict[str, float]] = {}
    playstyle_traits: dict[str, str] = {}

    @model_validator(mode="after")
    def _complete(self) -> "ImportProfile":
        missing = [c for c in REQUIRED_COLUMNS if c not in self.columns]
        if missing:
            raise ValueError(f"missing required columns: {missing}")
        unknown = set(self.columns) - set(REQUIRED_COLUMNS) - set(OPTIONAL_COLUMNS)
        if unknown:
            raise ValueError(f"unknown column fields: {sorted(unknown)}")
        for attr in [*self.attributes, *self.derived]:
            if attr not in ATTRIBUTES:
                raise ValueError(f"unknown attribute {attr!r}")
        overlap = set(self.attributes) & set(self.derived)
        if overlap:
            raise ValueError(f"attributes both imported and derived: {sorted(overlap)}")
        uncovered = set(ATTRIBUTES) - set(self.attributes) - set(self.derived)
        if uncovered:
            raise ValueError(f"attributes neither imported nor derived: {sorted(uncovered)}")
        available = set(self.attributes)
        for attr, rule in self.derived.items():
            needed = {i for term in rule.terms for i in term.inputs()}
            if not needed <= available:
                raise ValueError(f"{attr} uses {sorted(needed - available)} before they exist")
            available.add(attr)
        for effects in self.playstyle_effects.values():
            for attr in effects:
                if attr not in self.derived:
                    raise ValueError(f"playstyle effect on non-derived attribute {attr!r}")
        return self


def load_profile(path: Path) -> ImportProfile:
    return ImportProfile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
