"""Player development (design §16), applied on the first of every month.

Over a career a player grows towards his ceiling - his hidden potential, and for some a little
beyond it - reaches it around his own peak age, holds it, and declines from his early thirties,
his physical attributes first. A rare few, mostly very good players, are "ageless": their
decline starts years later and runs slower. Each player's peak age, decline age, ceiling and
agelessness are drawn once (``draw_traits``) and kept with his save.

A month's change in overall is split (data/config/rules/development.yaml):
  - ``specific_share`` of it lands on a few individual attributes, chosen by how much his
    position values them (in decline: physical ones first);
  - the rest builds up as ``progress`` until it makes a whole point of overall, when every
    attribute moves together by one.
So a growing player picks up the odd point here and there each month, and every so often his
whole game steps up.
"""

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from footsim.defs.development import DevelopmentDef
from footsim.defs.positions import PositionGroup
from footsim.domain.attributes import ATTR_INDEX, ATTRIBUTES, AttrGroup, attributes_in
from footsim.ratings.overall import RatingModel

FloatArray = npt.NDArray[np.float64]

_PHYSICAL_DECLINE = {"acceleration": 1.6, "sprint_speed": 1.7, "agility": 1.4, "stamina": 1.3,
                     "jumping": 1.2, "balance": 1.1, "natural_fitness": 1.0, "strength": 0.4}
_MENTAL = [ATTR_INDEX[a] for a in attributes_in(AttrGroup.MENTAL)]
_GOALKEEPING = [ATTR_INDEX[a] for a in attributes_in(AttrGroup.GOALKEEPING)]
MONTH = 1 / 12


@dataclass(frozen=True)
class DevelopmentInput:
    attrs: FloatArray  # (players, attributes)
    ages: FloatArray  # exact ages in years
    potential: FloatArray
    groups: list[PositionGroup]
    minutes: FloatArray  # minutes played in the past twelve months


@dataclass(frozen=True)
class Traits:
    peak_age: FloatArray
    decline_age: FloatArray
    ceiling_bonus: FloatArray
    ageless: npt.NDArray[np.bool_]


def draw_traits(rules: DevelopmentDef, potential: FloatArray,
                rng: np.random.Generator) -> Traits:
    """Each player's development traits, drawn once."""
    n = len(potential)
    bonus = np.zeros(n)
    roll = rng.random(n)
    edge = 0.0
    for chance, low, high in rules.beyond_potential:
        hit = (roll >= edge) & (roll < edge + chance)
        bonus[hit] = rng.integers(low, high + 1, size=int(hit.sum()))
        edge += chance
    ageless_chance = np.array([_lookup_from(rules.ageless_chance, p) for p in potential])
    return Traits(peak_age=rng.uniform(*rules.peak_age, size=n),
                  decline_age=rng.uniform(*rules.decline_start, size=n),
                  ceiling_bonus=bonus, ageless=rng.random(n) < ageless_chance)


def _lookup(table: list[tuple[int, float]], value: float, default: float) -> float:
    """The factor of the first band whose upper limit is at least ``value``."""
    for limit, factor in table:
        if value <= limit:
            return factor
    return default


def _lookup_from(table: list[tuple[int, float]], value: float) -> float:
    """The factor of the last band whose lower limit ``value`` has reached."""
    result = 0.0
    for limit, factor in table:
        if value >= limit:
            result = factor
    return result


def monthly_change(rules: DevelopmentDef, inp: DevelopmentInput, overall: FloatArray,
                   traits: Traits, rng: np.random.Generator) -> FloatArray:
    """Each player's change in overall this month."""
    change = np.zeros(len(inp.ages))
    for i, age in enumerate(inp.ages):
        start = traits.decline_age[i] + (rules.ageless_delay if traits.ageless[i] else 0.0)
        if age < start:  # growing towards his ceiling, then holding it
            gap = max(0.0, inp.potential[i] + traits.ceiling_bonus[i] - overall[i])
            if age <= traits.peak_age[i]:
                yearly = _lookup(rules.growth_by_age, age, rules.late_growth)
                yearly *= _lookup(rules.minutes, inp.minutes[i], rules.heavy_minutes)
            else:
                yearly = rules.late_growth
            change[i] = gap * (1 - (1 - min(0.95, yearly)) ** MONTH)
        else:
            years = int(age - start)
            yearly = rules.decline_by_year[min(years, len(rules.decline_by_year) - 1)]
            if traits.ageless[i]:
                yearly *= rules.ageless_slowdown
            change[i] = yearly * MONTH
    return change + rng.normal(0.0, rules.noise * math.sqrt(MONTH), size=len(change))


def _group_weights(model: RatingModel, group: PositionGroup) -> FloatArray:
    """How much the overall of ``group`` values each attribute (its roles, averaged)."""
    columns = [k for k, g in enumerate(model.role_groups) if g is group]
    scale = float(model.scale[columns].mean())
    result: FloatArray = model.weights[:, columns].mean(axis=1) * scale
    return result


def apply_month(rules: DevelopmentDef, model: RatingModel, inp: DevelopmentInput,
                traits: Traits, progress: FloatArray, rng: np.random.Generator
                ) -> tuple[FloatArray, FloatArray, npt.NDArray[np.int64]]:
    """One month's development. Returns the new attributes, the new progress, and each
    player's whole-point moves this month (+1 every attribute up, -1 down, 0 none)."""
    group_overalls = model.group_overalls(inp.attrs)
    overall = np.array([group_overalls[g][i] for i, g in enumerate(inp.groups)])
    change = monthly_change(rules, inp, overall, traits, rng)
    new = inp.attrs.copy()
    progress = progress.copy()
    moves = np.zeros(len(change), dtype=np.int64)
    weights = {g: _group_weights(model, g) for g in set(inp.groups)}
    decline_pick = np.full(len(ATTRIBUTES), 0.3)
    for attr, factor in _PHYSICAL_DECLINE.items():
        decline_pick[ATTR_INDEX[attr]] = factor
    decline_pick[_MENTAL] = 0.1
    for i, group in enumerate(inp.groups):
        w = weights[group]
        keeper = group is PositionGroup.GK
        every = np.ones(len(ATTRIBUTES), dtype=bool)  # what a whole-point move lifts
        if not keeper:
            every[_GOALKEEPING] = False
        specific = rules.specific_share * change[i]
        if specific > 0:  # a few attributes his position values pick up a point
            pick = w / w.sum()
            per_point = float((w * pick).sum())
        else:  # physical attributes go first
            pick = decline_pick * every
            pick = pick / pick.sum()
            per_point = float((w * pick).sum())
        if per_point > 0 and specific != 0:
            for _ in range(int(rng.poisson(abs(specific) / per_point))):
                a = int(rng.choice(len(ATTRIBUTES), p=pick))
                new[i, a] += 1 if specific > 0 else -1
        progress[i] += (1 - rules.specific_share) * change[i]
        step = float(w[every].sum())  # the overall a whole-point move makes
        while step > 0 and progress[i] >= step:
            new[i, every] += 1
            progress[i] -= step
            moves[i] += 1
        down = every.copy()
        down[_MENTAL] = False  # experience doesn't fade with the legs
        step_down = float(w[down].sum())
        while step_down > 0 and progress[i] <= -step_down:
            new[i, down] -= 1
            progress[i] += step_down
            moves[i] -= 1
    result: FloatArray = np.clip(new, 1, 99)
    return result, progress, moves
