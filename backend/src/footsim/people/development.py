"""Player development (design §16, first version).

Over a year every player moves toward (young) or away from (old) their peak:
  - under 28: a share of the gap to hidden potential, larger for younger players and for
    players who got minutes in the past year;
  - 29 and over: decline that accelerates with age, hitting physical attributes first.
It's applied a month at a time (``share`` 1/12), so squads change as the season goes. The
change is aimed at the player's overall in his main position group and spread over attributes
by how much that group values them, so a striker improves mostly as a striker.
"""

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from footsim.defs.loader import GameDefinitions
from footsim.defs.positions import PositionGroup
from footsim.domain.attributes import ATTR_INDEX, ATTRIBUTES, AttrGroup, attributes_in
from footsim.ratings.overall import RatingModel

GROWTH_RATE = [(19, 0.35), (21, 0.30), (23, 0.25), (25, 0.20), (27, 0.12)]  # (max age, share)
DECLINE = [(28, 0.0), (30, -0.8), (31, -1.4), (32, -2.0), (33, -2.6), (34, -3.2)]
LATE_DECLINE = -4.0
MINUTES_FACTOR = [(450, 0.55), (1350, 0.8), (2700, 1.0)]
HEAVY_MINUTES_FACTOR = 1.1
GROWTH_NOISE = 1.0

_PHYSICAL_DECLINE = {"acceleration": 1.6, "sprint_speed": 1.7, "agility": 1.4, "stamina": 1.3,
                     "jumping": 1.2, "balance": 1.1, "natural_fitness": 1.0, "strength": 0.4}
_MENTAL = set(attributes_in(AttrGroup.MENTAL))
_GOALKEEPING = set(attributes_in(AttrGroup.GOALKEEPING))


@dataclass(frozen=True)
class DevelopmentInput:
    attrs: npt.NDArray[np.float64]  # (players, attributes)
    ages: npt.NDArray[np.int64]
    potential: npt.NDArray[np.float64]
    groups: list[PositionGroup]
    minutes: npt.NDArray[np.float64]  # minutes played last season


def _lookup(table: list[tuple[int, float]], value: float, default: float) -> float:
    for limit, factor in table:
        if value <= limit:
            return factor
    return default


def target_changes(inp: DevelopmentInput, overall: npt.NDArray[np.float64],
                   rng: np.random.Generator, share: float = 1.0) -> npt.NDArray[np.float64]:
    """Each player's change in overall over ``share`` of a year. Growth closes the yearly share
    of the gap to potential, compounded so that twelve monthly steps add up to the year's."""
    changes = np.zeros(len(inp.ages))
    for i, age in enumerate(inp.ages):
        if age <= 27:
            gap = max(0.0, inp.potential[i] - overall[i])
            minutes = _lookup(MINUTES_FACTOR, inp.minutes[i], HEAVY_MINUTES_FACTOR)
            yearly = min(0.95, _lookup(GROWTH_RATE, age, 0.1) * minutes)
            changes[i] = gap * (1 - (1 - yearly) ** share)
        else:
            changes[i] = _lookup(DECLINE, age, LATE_DECLINE) * share
        changes[i] += rng.normal(0, GROWTH_NOISE * math.sqrt(share))
    return changes


def apply_development(defs: GameDefinitions, model: RatingModel, inp: DevelopmentInput,
                      rng: np.random.Generator, share: float = 1.0) -> npt.NDArray[np.float64]:
    """Returns the new attribute matrix after ``share`` of a year's development."""
    group_overalls = model.group_overalls(inp.attrs)
    overall = np.array([group_overalls[g][i] for i, g in enumerate(inp.groups)])
    change = target_changes(inp, overall, rng, share)
    new = inp.attrs.copy()
    for i, group in enumerate(inp.groups):
        weights = np.zeros(len(ATTRIBUTES))
        for attr, w in defs.group_weights[group].items():
            weights[ATTR_INDEX[attr]] = w
        if change[i] >= 0:
            shape = 0.4 + 1.6 * weights / weights.max()
            if group is not PositionGroup.GK:
                shape[[ATTR_INDEX[a] for a in _GOALKEEPING]] = 0.0
        else:
            shape = np.full(len(ATTRIBUTES), 0.8)
            for attr, factor in _PHYSICAL_DECLINE.items():
                shape[ATTR_INDEX[attr]] = factor
            shape[[ATTR_INDEX[a] for a in _MENTAL]] = 0.15
            shape[[ATTR_INDEX[a] for a in _GOALKEEPING]] = 0.8 if group is PositionGroup.GK else 0
        scale = model.scale[model.role_groups.index(group)]
        effect = scale * float(weights @ shape)
        if effect > 0:
            new[i] += change[i] * shape / effect
    # Stochastic rounding keeps small yearly changes unbiased instead of rounding them away.
    rounded = np.floor(new + rng.random(new.shape))
    result: npt.NDArray[np.float64] = np.clip(rounded, 1, 99)
    return result
