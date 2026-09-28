import math

import numpy as np
import pytest

from footsim.defs.loader import GameDefinitions, load_definitions
from footsim.defs.positions import PositionGroup
from footsim.domain.attributes import ATTRIBUTES, AttrGroup, attributes_in
from footsim.ratings.face import face_stats
from footsim.ratings.overall import (
    GroupScaling,
    OverallScaling,
    RatingModel,
    attribute_vector,
    familiarity_factor,
    role_weights,
)


@pytest.fixture(scope="module")
def defs() -> GameDefinitions:
    return load_definitions()


# The winger from the design brief: PAC 91 / SHO 79 / PAS 87 / DRI 89 / DEF 42 / PHY 76.
WINGER = {
    "acceleration": 93, "sprint_speed": 90, "agility": 90, "balance": 85, "strength": 70,
    "stamina": 84, "jumping": 70, "natural_fitness": 80,
    "first_touch": 89, "dribbling": 90, "short_passing": 88, "long_passing": 80, "crossing": 85,
    "finishing": 80, "shot_power": 80, "long_shots": 76, "volleys": 70, "curve": 86,
    "free_kicks": 70, "penalties": 70, "heading_accuracy": 55,
    "vision": 88, "composure": 84, "reactions": 86, "off_ball": 84, "anticipation": 84,
    "decisions": 84, "concentration": 70, "aggression": 62, "work_rate": 80, "teamwork": 80,
    "bravery": 65, "flair": 88,
    "marking": 38, "def_positioning": 40, "interceptions": 40, "standing_tackle": 42,
    "sliding_tackle": 35,
    **{gk: 10 for gk in attributes_in(AttrGroup.GOALKEEPING)},
}


def test_every_role_has_normalised_weights(defs: GameDefinitions) -> None:
    for role in defs.roles.values():
        weights = role_weights(defs, role)
        assert all(w > 0 for w in weights.values()), role.key
        assert math.isclose(sum(weights.values()), 1.0), role.key


def test_winger_is_excellent_wide_and_poor_at_centre_back(defs: GameDefinitions) -> None:
    model = RatingModel.build(defs)
    overall = model.group_overalls(attribute_vector(WINGER))
    assert overall[PositionGroup.W] >= 84
    assert overall[PositionGroup.CB] <= 62
    assert overall[PositionGroup.W] - overall[PositionGroup.CB] >= 25


def test_attribute_only_affects_roles_that_weight_it(defs: GameDefinitions) -> None:
    model = RatingModel.build(defs)
    base = attribute_vector(WINGER)
    better = base.copy()
    better[ATTRIBUTES.index("finishing")] += 10
    delta = model.role_overalls(better) - model.role_overalls(base)
    assert delta[model.role_index("poacher")] > 1.5
    assert delta[model.role_index("central_defender")] == pytest.approx(0.0)


def test_group_scaling_applies(defs: GameDefinitions) -> None:
    scaling = OverallScaling(groups={PositionGroup.ST: GroupScaling(scale=1.1, offset=-5.0)})
    plain = RatingModel.build(defs).role_overalls(attribute_vector(WINGER))
    scaled = RatingModel.build(defs, scaling).role_overalls(attribute_vector(WINGER))
    i = RatingModel.build(defs).role_index("poacher")
    assert scaled[i] == pytest.approx(plain[i] * 1.1 - 5.0)


def test_overalls_are_vectorised_over_players(defs: GameDefinitions) -> None:
    model = RatingModel.build(defs)
    batch = np.stack([attribute_vector(WINGER)] * 3)
    assert model.role_overalls(batch).shape == (3, len(model.role_keys))


@pytest.mark.parametrize(
    ("familiarity", "factor"), [(20, 1.0), (16, 0.97), (12, 0.93), (7, 0.85), (2, 0.75), (0, 0.65)]
)
def test_familiarity_bands(familiarity: int, factor: float) -> None:
    assert familiarity_factor(familiarity) == factor


def test_face_stats_match_design_example() -> None:
    stats = face_stats(WINGER)
    assert stats["PAC"] == 91
    assert stats["DEF"] < 45
