"""The error function without SciPy (SciPy has no iOS build).

A port of the Cephes ``erf``/``erfc`` that ``scipy.special.erf`` uses (``xsf/cephes/ndtr.h``).
``math.erf`` is a different algorithm and differs from SciPy's in the last bit on about half of
all inputs, which would move results. SciPy's arm64 build contracts each ``ans * x + coef``
polynomial step into a fused multiply-add, so the port uses ``math.fma`` at exactly those steps;
with that it matches ``scipy.special.erf`` bit for bit on darwin-arm64
(``tests/unit/test_special.py``).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from numpy.typing import NDArray

_MAXLOG = 7.09782712893383996732e2

_T = (
    9.60497373987051638749e0,
    9.00260197203842689217e1,
    2.23200534594684319226e3,
    7.00332514112805075473e3,
    5.55923013010394962768e4,
)
_U = (  # leading 1.0 implied
    3.35617141647503099647e1,
    5.21357949780152679795e2,
    4.59432382970980127987e3,
    2.26290000613890934246e4,
    4.92673942608635921086e4,
)
_P = (
    2.46196981473530512524e-10,
    5.64189564831068821977e-1,
    7.46321056442269912687e0,
    4.86371970985681366614e1,
    1.96520832956077098242e2,
    5.26445194995477358631e2,
    9.34528527171957607540e2,
    1.02755188689515710272e3,
    5.57535335369399327526e2,
)
_Q = (  # leading 1.0 implied
    1.32281951154744992508e1,
    8.67072140885989742329e1,
    3.54937778887819891062e2,
    9.75708501743205489753e2,
    1.82390916687909736289e3,
    2.24633760818710981792e3,
    1.65666309194161350182e3,
    5.57535340817727675546e2,
)
_R = (
    5.64189583547755073984e-1,
    1.27536670759978104416e0,
    5.01905042251180477414e0,
    6.16021097993053585195e0,
    7.40974269950448939160e0,
    2.97886665372100240670e0,
)
_S = (  # leading 1.0 implied
    2.26052863220117276590e0,
    9.39603524938001434673e0,
    1.20489539808096656605e1,
    1.70814450747565897222e1,
    9.60896809063285878198e0,
    3.36907645100081516050e0,
)


def _polevl(x: float, coef: tuple[float, ...]) -> float:
    ans = coef[0]
    for c in coef[1:]:
        ans = math.fma(ans, x, c)
    return ans


def _p1evl(x: float, coef: tuple[float, ...]) -> float:
    """As ``_polevl`` with an implied leading coefficient of 1.0."""
    ans = x + coef[0]
    for c in coef[1:]:
        ans = math.fma(ans, x, c)
    return ans


def erfc_scalar(a: float) -> float:
    """Cephes complementary error function of one float."""
    if math.isnan(a):
        return math.nan
    x = abs(a)
    if x < 1.0:
        return 1.0 - erf_scalar(a)
    z = -a * a
    if z < -_MAXLOG:
        return 2.0 if a < 0 else 0.0
    z = math.exp(z)
    if x < 8.0:
        p = _polevl(x, _P)
        q = _p1evl(x, _Q)
    else:
        p = _polevl(x, _R)
        q = _p1evl(x, _S)
    y = (z * p) / q
    if a < 0:
        y = 2.0 - y
    if y == 0.0:
        return 2.0 if a < 0 else 0.0
    return y


def erf_scalar(x: float) -> float:
    """Cephes error function of one float."""
    if math.isnan(x):
        return math.nan
    if x < 0.0:
        return -erf_scalar(-x)
    if abs(x) > 1.0:
        return 1.0 - erfc_scalar(x)
    z = x * x
    return x * _polevl(z, _T) / _p1evl(z, _U)


def erf(x: NDArray[Any] | float) -> NDArray[np.float64]:
    """``scipy.special.erf`` for a float array (or scalar), applied element by element."""
    arr = np.asarray(x, dtype=np.float64)
    out = np.array([erf_scalar(v) for v in arr.ravel().tolist()], dtype=np.float64)
    return out.reshape(arr.shape)
