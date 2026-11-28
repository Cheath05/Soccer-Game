"""The potential a manager sees stays on the 1-99 rating scale."""

from footsim.api.draft import potential_band
from footsim.scouting.estimates import (
    OTHER_CLUB_KNOWLEDGE,
    OWN_CLUB_KNOWLEDGE,
    RATING_MAX,
    potential_range,
)


def test_potential_range_never_goes_above_99() -> None:
    """A top prospect whose scouts' bias runs high used to be shown as, say, 97-104."""
    worst = 0
    for player_id in range(300):
        for true_potential in (90, 95, 99):
            for age in (16, 18, 21, 25, 30):
                for knowledge in (OWN_CLUB_KNOWLEDGE, OTHER_CLUB_KNOWLEDGE):
                    current = min(true_potential, 60 + 2 * age)
                    low, high = potential_range(true_potential, current, age, knowledge,
                                                seed=7, player_id=player_id)
                    assert 1 <= low <= high <= RATING_MAX
                    assert low >= min(round(current), RATING_MAX)  # never below his overall
                    worst = max(worst, high)
    assert worst == RATING_MAX  # the cases tried do reach the top of the scale


def test_potential_range_at_the_top_of_the_scale() -> None:
    """A 99 overall can't have a range above himself."""
    assert potential_range(99, 99.0, 29, OWN_CLUB_KNOWLEDGE, 7, 1) == (99, 99)


def test_draft_band_stays_on_the_scale() -> None:
    assert potential_band(72.4, 60) == (70, 75)
    assert potential_band(64.0, 68) == (68, 68)  # never below his overall
    assert potential_band(97.0, 70) == (95, 99)  # was 95-100
    assert potential_band(101.3, 70) == (99, 99)  # was 100-105
