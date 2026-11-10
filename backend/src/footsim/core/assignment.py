"""Linear sum assignment without SciPy (SciPy has no iOS build).

A literal port of SciPy 1.18.1's ``scipy/optimize/rectangular_lsap/rectangular_lsap.cpp``
(Crouse's shortest augmenting path algorithm) and of the thin wrapper around it. It is kept
step-for-step identical on purpose. Ties are routine in this game (identical centre-back
columns, fixed slots at exactly 1e6, familiarity bands times 100), and a different exact solver
would pick another tied optimum and move the engine's golden values. So the *assignment* has to
match SciPy's, not just its cost. What must not change:

- the ``remaining`` list is filled in reverse order;
- the tie rule: a column equal to the lowest cost wins only if it is unassigned;
- the dual updates, in the same order and with the same arithmetic;
- a tall matrix is transposed, and its result re-ordered by a final argsort.

``tests/unit/test_assignment.py`` checks it against SciPy on 100,000 matrices.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

_INF = float("inf")


def _augmenting_path(
    nc: int,
    cost: list[list[float]],
    u: list[float],
    v: list[float],
    path: list[int],
    row4col: list[int],
    shortest: list[float],
    i: int,
    in_sr: list[bool],
    in_sc: list[bool],
) -> tuple[int, float]:
    """Find the shortest augmenting path from row ``i``. Returns (sink, min_val); sink -1 if none.

    ``shortest``, ``in_sr`` and ``in_sc`` are reset here and read by the caller afterwards.
    """
    min_val = 0.0
    # Filled in reverse so that a constant cost matrix solves to the identity (SciPy #11602).
    remaining = list(range(nc - 1, -1, -1))
    num_remaining = nc
    for k in range(len(in_sr)):
        in_sr[k] = False
    for k in range(nc):
        in_sc[k] = False
        shortest[k] = _INF

    sink = -1
    while sink == -1:
        index = -1
        lowest = _INF
        in_sr[i] = True
        cost_i = cost[i]
        u_i = u[i]

        for it in range(num_remaining):
            j = remaining[it]
            r = min_val + cost_i[j] - u_i - v[j]
            if r < shortest[j]:
                path[j] = i
                shortest[j] = r
            # Among columns tied for the lowest cost, prefer one that is a new sink.
            s = shortest[j]
            if s < lowest or (s == lowest and row4col[j] == -1):
                lowest = s
                index = it

        min_val = lowest
        if min_val == _INF:  # infeasible cost matrix
            return -1, min_val

        j = remaining[index]
        if row4col[j] == -1:
            sink = j
        else:
            i = row4col[j]

        in_sc[j] = True
        num_remaining -= 1
        remaining[index] = remaining[num_remaining]

    return sink, min_val


def linear_sum_assignment(
    cost_matrix: NDArray[Any], maximize: bool = False
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """Solve the linear sum assignment problem exactly as ``scipy.optimize`` does.

    Returns ``(row_ind, col_ind)`` as int64 arrays with ``row_ind`` sorted; for a tall matrix
    only the assigned rows appear. NaN and -inf entries aren't checked for (the callers never
    produce them); an infeasible matrix raises ``ValueError`` as SciPy's does.
    """
    arr = np.asarray(cost_matrix, dtype=np.float64)
    if arr.ndim != 2:
        raise ValueError(f"expected a matrix (2-D array), got a {arr.ndim}-D array")
    nr, nc = arr.shape
    if nr == 0 or nc == 0:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)

    # A tall rectangular cost matrix must be transposed.
    transpose = nc < nr
    if transpose:
        arr = arr.T
        nr, nc = nc, nr
    if maximize:
        arr = -arr
    cost: list[list[float]] = arr.tolist()

    u = [0.0] * nr
    v = [0.0] * nc
    shortest = [_INF] * nc
    path = [-1] * nc
    col4row = [-1] * nr
    row4col = [-1] * nc
    in_sr = [False] * nr
    in_sc = [False] * nc

    for cur_row in range(nr):
        sink, min_val = _augmenting_path(
            nc, cost, u, v, path, row4col, shortest, cur_row, in_sr, in_sc)
        if sink < 0:
            raise ValueError("cost matrix is infeasible")

        # Update the dual variables.
        u[cur_row] += min_val
        for i in range(nr):
            if in_sr[i] and i != cur_row:
                u[i] += min_val - shortest[col4row[i]]
        for j in range(nc):
            if in_sc[j]:
                v[j] -= min_val - shortest[j]

        # Augment the previous solution.
        j = sink
        while True:
            i = path[j]
            row4col[j] = i
            col4row[i], j = j, col4row[i]
            if i == cur_row:
                break

    if transpose:
        # col4row is a permutation prefix (all distinct), so the sort order is unambiguous.
        order = sorted(range(nr), key=col4row.__getitem__)
        a = [col4row[k] for k in order]
        b = order
    else:
        a = list(range(nr))
        b = col4row
    return np.array(a, dtype=np.int64), np.array(b, dtype=np.int64)
