"""Rating responses read from a batch report (calibration/responses.py)."""

import json
from pathlib import Path

import pytest

from footsim.calibration.responses import responses


def test_a_slope_per_point_of_advantage(tmp_path: Path) -> None:
    # Each point of XI advantage is worth exactly a tenth of a goal and a shot here.
    matches = []
    for k, gap in enumerate((-4.0, -2.0, 0.0, 2.0, 4.0) * 4):
        home_goals = round(1.0 + 0.1 * gap, 3)
        matches.append({"index": k, "arm": "baseline", "xi_rating": [70 + gap, 70.0],
                        "score": [home_goals, 1.0], "xg": [1.0, 1.0],
                        "shots": [10 + gap, 10.0], "possession": [0.5, 0.5]})
    report = tmp_path / "r.json"
    report.write_text(json.dumps({"arms": {"baseline": {}}, "matches": matches}))
    out = responses(report)
    assert out["goals"][0] == pytest.approx(0.05, abs=1e-9)  # half on each side of the gap
    assert out["shots"][0] == pytest.approx(0.5, abs=1e-9)
    assert out["possession"][0] == pytest.approx(0.0, abs=1e-12)
