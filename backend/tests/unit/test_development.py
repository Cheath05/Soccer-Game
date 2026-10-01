"""Player development runs a month at a time: twelve monthly steps add up to a year's."""

import numpy as np

from footsim.defs.positions import PositionGroup
from footsim.domain.attributes import ATTRIBUTES
from footsim.people.development import DevelopmentInput, target_changes


def _players(age: int, minutes: float) -> DevelopmentInput:
    n = 4
    return DevelopmentInput(attrs=np.full((n, len(ATTRIBUTES)), 60.0),
                            ages=np.full(n, age), potential=np.full(n, 80.0),
                            groups=[PositionGroup.CM] * n, minutes=np.full(n, minutes))


class _Quiet:
    """A generator with no noise, to compare the systematic part."""

    def normal(self, loc: float, scale: float) -> float:
        return 0.0


def test_twelve_months_of_growth_add_up_to_a_year() -> None:
    young = _players(19, 2000.0)
    overall = np.full(4, 60.0)
    yearly = target_changes(young, overall, _Quiet(), share=1.0)  # type: ignore[arg-type]
    total = np.zeros(4)
    for _ in range(12):  # the gap closes a little each month
        step = target_changes(young, overall + total, _Quiet(), share=1 / 12)  # type: ignore[arg-type]
        total += step
    assert np.allclose(total, yearly, rtol=1e-6)
    assert (yearly > 0).all()


def test_decline_spreads_evenly_over_the_year() -> None:
    old = _players(33, 2500.0)
    overall = np.full(4, 75.0)
    yearly = target_changes(old, overall, _Quiet(), share=1.0)  # type: ignore[arg-type]
    monthly = target_changes(old, overall, _Quiet(), share=1 / 12)  # type: ignore[arg-type]
    assert (yearly < 0).all()
    assert np.allclose(monthly * 12, yearly)
