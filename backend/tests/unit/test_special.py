"""The Cephes ``erf`` port equals ``scipy.special.erf`` bit for bit.

Bit equality depends on the platform's fused multiply-add contraction and ``exp``, so the
comparison runs only where the game's results are pinned: darwin-arm64.
"""

import math
import platform
import sys

import numpy as np
import pytest
from scipy.special import erf as scipy_erf

from footsim.core.special import erf, erf_scalar, erfc_scalar

darwin_arm64 = pytest.mark.skipif(
    not (sys.platform == "darwin" and platform.machine() == "arm64"),
    reason="bit-for-bit equality with SciPy's erf is only claimed on darwin-arm64")


@darwin_arm64
def test_erf_matches_scipy_bit_for_bit() -> None:
    rng = np.random.default_rng(20261110)
    x = np.concatenate([
        rng.random(300_000),                        # [0, 1): the rational T/U branch
        rng.uniform(1.0, 8.0, 150_000),             # the P/Q branch
        rng.uniform(8.0, 28.0, 50_000),             # the R/S branch and the underflow edge
        rng.normal(0.0, 2.0, 150_000),              # both signs, clustered near zero
        10.0 ** rng.uniform(-300, 2, 100_000),      # tiny to large, as slack/spread ratios are
        -(10.0 ** rng.uniform(-300, 2, 50_000)),
        np.array([0.0, -0.0, 1.0, -1.0, np.nextafter(1.0, 0), np.nextafter(1.0, 2), 8.0, -8.0,
                  26.0, 26.6, 26.7, 27.0, 1e6, 5e-324, np.inf, -np.inf]),
    ])
    assert len(x) == 800_016
    ours, ref = erf(x), scipy_erf(x)
    assert ours.dtype == ref.dtype == np.float64
    differs = ours.view(np.uint64) != ref.view(np.uint64)
    assert not differs.any(), (
        f"{int(differs.sum())} of {len(x)} differ, first at x={x[differs][0]!r}")


def test_erf_shapes_and_special_values() -> None:
    grid = np.linspace(-3, 3, 12).reshape(3, 4)
    out = erf(grid)
    assert out.shape == (3, 4)
    assert np.allclose(out, np.vectorize(math.erf)(grid), rtol=0, atol=1e-15)
    assert erf(0.5).shape == ()
    assert erf(np.array([], dtype=np.float64)).shape == (0,)
    assert math.isnan(erf_scalar(math.nan)) and math.isnan(erfc_scalar(math.nan))
    assert erf_scalar(math.inf) == 1.0 and erf_scalar(-math.inf) == -1.0
    assert erfc_scalar(30.0) == 0.0 and erfc_scalar(-30.0) == 2.0
    assert erf_scalar(-0.3) == -erf_scalar(0.3)
    assert erfc_scalar(0.25) == 1.0 - erf_scalar(0.25)
