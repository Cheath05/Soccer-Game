"""Generates the player values no dataset provides, following data/config/world_build.yaml.
All functions take their random generator explicitly so world builds are reproducible."""

import math
from datetime import date

import numpy as np

from footsim.defs.finance import WageLevel
from footsim.defs.world_build import (
    ContractRules,
    PersonalityRules,
    PhysiqueRules,
    PotentialRules,
    ReputationRules,
)
from footsim.domain.personality import PERSONALITY_TRAITS, TRAIT_MAX, TRAIT_MIN


def age_on(birth: date, day: date) -> int:
    return day.year - birth.year - ((day.month, day.day) < (birth.month, birth.day))


def draw_potential(
    overall: float, age: int, rules: PotentialRules, rng: np.random.Generator
) -> int:
    youngest = min(rules.growth_by_age)
    age = max(age, youngest)
    mean = rules.growth_by_age.get(age, 0.0)
    current = round(overall)
    if mean <= 0:
        return current
    growth = max(0.0, float(rng.normal(mean, rules.sd_ratio * mean + rules.sd_floor)))
    growth = min(growth, rules.headroom_share * (99 - overall))
    potential = overall + growth
    elite_start = max(rules.elite_threshold, overall)
    if potential > elite_start:
        potential = elite_start + (potential - elite_start) * rules.elite_compression
    return max(current, min(rules.max_potential, round(potential)))


def estimate_height(
    position: str, attrs: dict[str, int], rules: PhysiqueRules, rng: np.random.Generator
) -> int:
    height = rules.height_by_position[position]
    if position != "GK":
        height += sum(
            per_point * (attrs[attr] - rules.attribute_reference)
            for attr, per_point in rules.height_per_point.items()
        )
    height += float(rng.normal(0.0, rules.height_sd))
    low, high = rules.height_range
    return int(min(high, max(low, round(height))))


def estimate_weight(
    height_cm: int, attrs: dict[str, int], rules: PhysiqueRules, rng: np.random.Generator
) -> int:
    bmi = (
        rules.bmi_mean
        + rules.bmi_per_strength_point * (attrs["strength"] - rules.attribute_reference)
        + float(rng.normal(0.0, rules.bmi_sd))
    )
    low, high = rules.weight_range
    return int(min(high, max(low, round(bmi * (height_cm / 100) ** 2))))


def draw_personality(
    overall: float, rules: PersonalityRules, rng: np.random.Generator
) -> dict[str, int]:
    traits = {}
    for trait in PERSONALITY_TRAITS:
        dist = rules.overrides.get(trait, rules.default)
        shift = rules.overall_effect_per_point.get(trait, 0.0) * (overall - rules.overall_reference)
        value = float(rng.normal(dist.mean + shift, dist.sd))
        traits[trait] = int(min(TRAIT_MAX, max(TRAIT_MIN, round(value))))
    return traits


def generated_contract_end(
    age: int, season_start: date, rules: ContractRules, rng: np.random.Generator
) -> date:
    band = next(b for b in rules.remaining_years if age <= b.max_age)
    years = int(rng.integers(band.min_years, band.max_years + 1))
    return date(season_start.year + years, 6, 30)


def weekly_wage_cents(
    overall: float, level: WageLevel, minimum_weekly: float, rng: np.random.Generator
) -> int:
    wage = level.wage_for(overall) * math.exp(float(rng.normal(0.0, level.spread_sd)))
    wage = max(minimum_weekly, wage)
    step = 50 if wage < 10_000 else 500
    return int(round(wage / step) * step) * 100


def club_reputation(top_overalls: list[float], rules: ReputationRules) -> int:
    if not top_overalls:
        return 1
    best = sorted(top_overalls, reverse=True)[: rules.club_top_players]
    mean = sum(best) / len(best)
    value = rules.club_base + rules.club_per_point * (mean - rules.club_reference_overall)
    return int(min(99, max(1, round(value))))


def player_reputation(overall: float, club_rep: int, rules: ReputationRules) -> int:
    value = (
        1
        + rules.player_per_point * (overall - rules.player_reference_overall)
        + rules.player_club_weight * (club_rep - 50)
    )
    return int(min(99, max(1, round(value))))
