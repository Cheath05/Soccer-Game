"""Role and position overall ratings.

Role overall = weighted sum of attributes (weights = position group base + role modifiers,
renormalised), then a per-group linear scaling fitted so our numbers sit on a familiar
1-99 scale (data/config/calibration/overall_scaling.yaml). Position overall = the best
role overall in that position's group.

Overall is a summary for UI and AI decisions. The match engine reads attributes directly.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import yaml
from pydantic import BaseModel, ConfigDict

from footsim.defs.loader import GameDefinitions
from footsim.defs.positions import PositionGroup
from footsim.defs.roles import RoleDef
from footsim.domain.attributes import ATTR_INDEX, ATTRIBUTES

FloatArray = npt.NDArray[np.float64]

# (minimum familiarity, multiplier): natural, accomplished, competent, awkward, unconvincing.
_FAMILIARITY_BANDS = ((18, 1.00), (15, 0.97), (11, 0.93), (6, 0.85), (1, 0.75))
_UNFAMILIAR = 0.65


def familiarity_factor(familiarity: int) -> float:
    for threshold, factor in _FAMILIARITY_BANDS:
        if familiarity >= threshold:
            return factor
    return _UNFAMILIAR


def role_weights(defs: GameDefinitions, role: RoleDef) -> dict[str, float]:
    base = defs.group_weights[role.group]
    combined = {a: base.get(a, 0.0) + role.weight_modifiers.get(a, 0.0) for a in ATTRIBUTES}
    clipped = {a: max(0.0, w) for a, w in combined.items() if w > 0}
    total = sum(clipped.values())
    return {a: w / total for a, w in clipped.items()}


class GroupScaling(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scale: float = 1.0
    offset: float = 0.0


class OverallScaling(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    groups: dict[PositionGroup, GroupScaling] = {}

    def for_group(self, group: PositionGroup) -> GroupScaling:
        return self.groups.get(group, GroupScaling())


def load_overall_scaling(path: Path) -> OverallScaling:
    if not path.exists():
        return OverallScaling()
    return OverallScaling.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class RatingModel:
    role_keys: tuple[str, ...]
    role_groups: tuple[PositionGroup, ...]
    weights: FloatArray  # (n_attributes, n_roles)
    scale: FloatArray  # (n_roles,)
    offset: FloatArray  # (n_roles,)

    @classmethod
    def build(cls, defs: GameDefinitions, scaling: OverallScaling | None = None) -> "RatingModel":
        scaling = scaling or OverallScaling()
        group_order = list(PositionGroup)
        roles = sorted(defs.roles.values(), key=lambda r: (group_order.index(r.group), r.key))
        weights = np.zeros((len(ATTRIBUTES), len(roles)))
        for j, role in enumerate(roles):
            for attr, w in role_weights(defs, role).items():
                weights[ATTR_INDEX[attr], j] = w
        return cls(
            role_keys=tuple(r.key for r in roles),
            role_groups=tuple(r.group for r in roles),
            weights=weights,
            scale=np.array([scaling.for_group(r.group).scale for r in roles]),
            offset=np.array([scaling.for_group(r.group).offset for r in roles]),
        )

    def role_overalls(self, attrs: FloatArray) -> FloatArray:
        """attrs: (n_players, n_attributes) or (n_attributes,) -> overalls per role."""
        raw = np.asarray(attrs, dtype=np.float64) @ self.weights
        result: FloatArray = np.clip(raw * self.scale + self.offset, 1.0, 99.0)
        return result

    def group_overalls(self, attrs: FloatArray) -> dict[PositionGroup, FloatArray]:
        """Best role overall per position group."""
        per_role = self.role_overalls(attrs)
        groups = np.array(self.role_groups)
        return {g: per_role[..., groups == g].max(axis=-1) for g in PositionGroup}

    def role_index(self, key: str) -> int:
        return self.role_keys.index(key)


def attribute_vector(values: Mapping[str, float]) -> FloatArray:
    """Mapping of attribute -> value to a vector in canonical order (missing -> 0)."""
    vec = np.zeros(len(ATTRIBUTES))
    for attr, value in values.items():
        vec[ATTR_INDEX[attr]] = value
    return vec
