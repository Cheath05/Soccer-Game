"""B2's comparison of the two engines: the rating response fit."""

import numpy as np
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


def test_the_fast_engine_keeps_the_measured_surrogate_behaviour() -> None:
    """B2 (6 Oct): on the same fixtures the two engines split results alike and respond to a
    rating gap alike (pooled Premier League and League Two fixtures: +0.24 goal difference a
    point in the agent engine, +0.22 in the fast one), and the fast engine scores at the real
    level. Synthetic sides, both engines' inputs: the fast engine must keep that behaviour."""
    from footsim.core.rng import derive_rng
    from footsim.match.synthetic import synthetic_sheet
    from footsim.world.context import get_world

    world = get_world()
    gaps, scores = [], []
    for k in range(600):
        home_q, away_q = 64.0 + (k % 7) * 3.0, 64.0 + (k // 7 % 7) * 3.0
        home = synthetic_sheet(world.defs, world.picker, 1 + k % 5, home_q, seed=k)
        away = synthetic_sheet(world.defs, world.picker, 7 + k % 5, away_q, seed=k + 1)
        report = world.quick.play(home, away, derive_rng(3, "surrogate", k))
        rating = [float(np.mean([sp.rating for sp in s.starters])) for s in (home, away)]
        gaps.append(rating[0] - rating[1])
        scores.append((report.home_goals, report.away_goals))
    response = fit_response(gaps, scores)
    assert 0.12 <= response.per_point <= 0.35
    assert 0.15 <= response.home_edge <= 0.6
    assert 2.4 <= response.goals <= 3.6
