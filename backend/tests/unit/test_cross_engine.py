"""B2's comparison of the two engines: the rating response fit."""

import pytest

from footsim.calibration.cross_engine import fit_response


def test_fit_response_reads_home_edge_and_per_point() -> None:
    # Mean goal differences -1, 0.5 and 1.5 at gaps -10, 0 and 10: a line through 1/3 at an
    # even gap, rising 0.125 a point.
    gaps = [-10.0, 0.0, 10.0, -10.0, 0.0, 10.0]
    scores = [(1, 2), (1, 1), (2, 1), (0, 1), (2, 1), (3, 1)]
    response = fit_response(gaps, scores)
    assert response.matches == 6
    assert response.goals == pytest.approx(16 / 6)
    assert response.home_win == pytest.approx(3 / 6) and response.draw == pytest.approx(1 / 6)
    assert response.home_edge == pytest.approx(1 / 3)
    assert response.per_point == pytest.approx(0.125)
