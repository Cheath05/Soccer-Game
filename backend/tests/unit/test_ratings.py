import math
from datetime import date

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
    # His pace and passing count a little at centre-back since P14 (62 before), and being out of
    # position costs him more on top (familiarity_factor)
    assert overall[PositionGroup.CB] <= 66
    assert overall[PositionGroup.W] - overall[PositionGroup.CB] >= 20


def test_attribute_only_affects_roles_that_weight_it(defs: GameDefinitions) -> None:
    model = RatingModel.build(defs, face_blend=0.0)  # the roles alone
    base = attribute_vector(WINGER)
    better = base.copy()
    better[ATTRIBUTES.index("finishing")] += 10
    delta = model.role_overalls(better) - model.role_overalls(base)
    assert delta[model.role_index("poacher")] > 1.5
    assert delta[model.role_index("central_defender")] == pytest.approx(0.0)


def _centre_back(pace: float, passing: float, shooting: float, dribbling: float) -> np.ndarray:
    """A centre-back with DEF and PHY about 80, and the rest as given."""
    attrs = dict.fromkeys(ATTRIBUTES, 60.0)
    attrs.update(dict.fromkeys(attributes_in(AttrGroup.GOALKEEPING), 10.0))
    attrs.update(dict.fromkeys(("marking", "def_positioning", "standing_tackle", "interceptions",
                                "sliding_tackle", "heading_accuracy", "strength", "stamina",
                                "aggression", "jumping"), 80.0))
    attrs.update({"acceleration": pace, "sprint_speed": pace})
    attrs.update({a: passing for a in ("short_passing", "vision", "long_passing", "crossing",
                                       "curve", "free_kicks")})
    attrs.update({a: shooting for a in ("finishing", "shot_power", "long_shots", "volleys",
                                        "penalties")})
    attrs.update({a: dribbling for a in ("dribbling", "first_touch", "agility", "balance")})
    return attribute_vector(attrs)


def test_every_headline_rating_counts_towards_the_overall(defs: GameDefinitions) -> None:
    """The user's report (1 Oct): a player with only two headline ratings at 70+ rated 76. A
    one-dimensional centre-back now sits further below a rounded one with the same defending."""
    narrow = _centre_back(pace=45, passing=55, shooting=35, dribbling=50)
    rounded = _centre_back(pace=72, passing=72, shooting=60, dribbling=70)
    before = RatingModel.build(defs, face_blend=0.0).group_overalls(np.stack([narrow, rounded]))
    after = RatingModel.build(defs).group_overalls(np.stack([narrow, rounded]))
    gap_before = before[PositionGroup.CB][1] - before[PositionGroup.CB][0]
    gap_after = after[PositionGroup.CB][1] - after[PositionGroup.CB][0]
    assert gap_after >= gap_before + 3


def test_key_headline_ratings_still_matter_most(defs: GameDefinitions) -> None:
    for group, weights in defs.overall.face_weights.items():
        key = "REF" if group is PositionGroup.GK else max(weights, key=lambda k: weights[k])
        assert weights[key] >= 0.2, group


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


def test_scaling_keeps_the_sources_mean_and_spread(defs: GameDefinitions) -> None:
    """Each group's scaling matches the source's mean and spread, so the best players still
    reach the top of the scale."""
    from footsim.calibration.overall import fit_overall_scaling
    from footsim.importers.records import SourcePlayer

    rng = np.random.default_rng(0)
    players = []
    for i in range(60):
        quality = rng.uniform(50, 85)
        attrs = {a: int(np.clip(quality + rng.normal(0, 8), 1, 99)) for a in ATTRIBUTES}
        players.append(SourcePlayer(
            source="test", source_id=str(i), first_name="A", last_name=str(i), known_as=None,
            birth_date=date(2000, 1, 1), nationality="England",
            club="Club", league="League", position="ST", alt_positions=[],
            preferred_foot="Right", weak_foot=3, skill_moves=3, height_cm=180, weight_kg=75,
            source_overall=int(round(quality)), playstyles=[], attrs=attrs))
    (fit,) = fit_overall_scaling(defs, players)
    scaling = OverallScaling(groups={PositionGroup.ST: GroupScaling(scale=fit.scale,
                                                                    offset=fit.offset)})
    matrix = np.array([[p.attrs[a] for a in ATTRIBUTES] for p in players], dtype=float)
    scaled = RatingModel.build(defs, scaling).group_overalls(matrix)[PositionGroup.ST]
    source = np.array([p.source_overall for p in players], dtype=float)
    assert scaled.mean() == pytest.approx(source.mean(), abs=1e-6)
    assert scaled.std() == pytest.approx(source.std(), abs=1e-6)
