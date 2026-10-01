"""Pitch geometry and the value models the agent engine reasons with.

All functions here work in a team's *attacking frame*: x runs from the team's own goal line
(0) to the opponent's (105), y across the pitch (0-68). The engine converts to and from
pitch coordinates.
"""

import math

import numpy as np
import numpy.typing as npt

LENGTH = 105.0
WIDTH = 68.0
MID_X = LENGTH / 2
MID_Y = WIDTH / 2
GOAL_HALF = 3.66
GOAL_HEIGHT = 2.44
BOX_DEPTH = 16.5
BOX_HALF = 20.16
SIX_DEPTH = 5.5
SIX_HALF = 9.16
PENALTY_SPOT = LENGTH - 11.0

Array = npt.NDArray[np.float64]


def goal_angle(x: float, y: float) -> float:
    """Angle (radians) subtended by the goal posts from (x, y)."""
    dx = max(LENGTH - x, 0.05)
    return abs(math.atan2(MID_Y + GOAL_HALF - y, dx) - math.atan2(MID_Y - GOAL_HALF - y, dx))


def expected_goal(x: float, y: float, header: bool = False, pressure: float = 0.0) -> float:
    """Chance quality from position: a logistic model on angle and distance, fitted so that
    the penalty spot is ~0.3, the edge of the box ~0.08 and 25 m ~0.03 in open play."""
    distance = math.hypot(LENGTH - x, MID_Y - y)
    z = -1.2 + 2.5 * goal_angle(x, y) - 0.11 * distance
    value = 1.0 / (1.0 + math.exp(-z))
    if header:
        value *= 0.55
    value *= 1.0 - 0.5 * pressure
    return float(min(0.8, max(0.003, value)))


def threat(x: Array | float, y: Array | float) -> Array:
    """Value of having the ball at (x, y): mostly driven by closeness to the opponent goal."""
    distance = np.hypot(LENGTH - np.asarray(x), MID_Y - np.asarray(y))
    progress = np.asarray(x) / LENGTH
    result: Array = 0.004 + 0.30 * np.exp(-distance / 12.0) + 0.03 * progress**2
    return result


def loss_cost(x: Array | float, y: Array | float) -> Array:
    """How costly losing the ball at (x, y) is: large near our own goal."""
    result: Array = 0.02 + 0.32 * np.exp(-np.hypot(np.asarray(x), np.asarray(y) - MID_Y) / 16.0)
    return result


def in_box(x: float, y: float) -> bool:
    """Inside the penalty area the team is attacking."""
    return x >= LENGTH - BOX_DEPTH and abs(y - MID_Y) <= BOX_HALF


def in_own_box(x: float, y: float) -> bool:
    return x <= BOX_DEPTH and abs(y - MID_Y) <= BOX_HALF


def norm(v: Array) -> float:
    """A vector's length, computed exactly as np.linalg.norm computes it (the square root of
    v·v) but without its argument handling, which was the engine's biggest single cost."""
    if v.ndim != 1:
        raise ValueError("norm takes one vector; use norms for rows")
    return math.sqrt(float(v.dot(v)))


def norms(m: Array, axis: int) -> Array:
    """Lengths along ``axis``, computed exactly as np.linalg.norm(m, axis=axis) computes them."""
    result: Array = np.sqrt(np.add.reduce(m * m, axis=axis))
    return result
