"""The multi-season market report (calibration/market_report.py) sorts moves into windows."""

from footsim.calibration.market_report import _window


def test_moves_fall_in_the_summer_or_the_winter_window() -> None:
    assert _window("2026-07-01") == _window("2026-09-01") == "summer"
    assert _window("2026-05-28") == _window("2026-10-31") == "summer"  # early and late windows
    assert _window("2027-01-15") == _window("2027-02-02") == "winter"
    assert _window("2026-12-31") == _window("2027-04-01") == "winter"
