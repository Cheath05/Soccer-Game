"""The pure-Python assignment solver picks exactly SciPy's assignment, ties included.

SciPy has no iOS build, so the game ships ``footsim.core.assignment`` instead. The engine's
golden values depend on *which* tied optimum is chosen, so equal cost isn't enough: the row and
column arrays must be identical. SciPy stays in the dev group as the reference.
"""

from collections.abc import Iterator

import numpy as np
import numpy.typing as npt
import pytest
from scipy.optimize import linear_sum_assignment as scipy_lsa

from footsim.core.assignment import linear_sum_assignment

Batch = npt.NDArray[np.float64]

# Engine re-shapes (10 outfielders or 11 players into as many slots), the lineup picker (a squad
# into 11 slots, so tall), and assorted wide, tall and degenerate shapes.
SHAPES: list[tuple[int, int]] = [
    (10, 10), (11, 11), (30, 11), (25, 11), (18, 11), (12, 11), (11, 30), (11, 14), (7, 11),
    (4, 9), (9, 4), (3, 3), (2, 5), (5, 2), (1, 1), (1, 6), (6, 1),
]
PER_KIND_AND_SHAPE = 840  # 7 kinds x 17 shapes x 840 = 99,960, plus the 40 fixed cases below
BANDS = np.array([0.0, 0.25, 0.5, 0.75, 1.0])


def _uniform(rng: np.random.Generator, n: int, r: int, c: int) -> Batch:
    return rng.random((n, r, c)) * 100


def _small_integers(rng: np.random.Generator, n: int, r: int, c: int) -> Batch:
    return rng.integers(0, 4, (n, r, c)).astype(np.float64)


def _constant(rng: np.random.Generator, n: int, r: int, c: int) -> Batch:
    return np.broadcast_to(rng.integers(-3, 4, (n, 1, 1)).astype(np.float64), (n, r, c)).copy()


def _identical_columns(rng: np.random.Generator, n: int, r: int, c: int) -> Batch:
    """Columns copied from a few originals: two centre-backs in a 4-4-2 score the same."""
    base = np.round(rng.random((n, r, c)) * 100, 1)
    source = rng.integers(0, max(1, c // 2), (n, c))
    return np.take_along_axis(base, np.broadcast_to(source[:, None, :], (n, r, c)), axis=2)


def _banded(rng: np.random.Generator, n: int, r: int, c: int) -> Batch:
    """The engine's re-shape score: a familiarity band times 100, plus the player's rating."""
    rating = rng.integers(40, 95, (n, r, 1)) / 100
    return np.asarray(BANDS[rng.integers(0, len(BANDS), (n, r, c))] * 100 + rating)


def _fixed_slots(rng: np.random.Generator, n: int, r: int, c: int) -> Batch:
    """The picker's score with some slots forced to exactly 1e6 (sometimes clashing)."""
    score = np.round(rng.random((n, r, c)) * 60 + 30, 2)
    for _ in range(3):
        on = rng.random(n) < 0.7
        score[on, rng.integers(0, r, n)[on], rng.integers(0, c, n)[on]] = 1e6
    return score


def _banded_fixed_duplicated(rng: np.random.Generator, n: int, r: int, c: int) -> Batch:
    """Everything at once: bands, duplicate columns and duplicate rows, and forced slots."""
    score = _banded(rng, n, r, c)
    source = rng.integers(0, max(1, c - 2), (n, c))
    score = np.take_along_axis(score, np.broadcast_to(source[:, None, :], (n, r, c)), axis=2)
    if r > 1:
        score[:, r - 1, :] = score[:, 0, :]
    on = rng.random(n) < 0.5
    score[on, rng.integers(0, r, n)[on], rng.integers(0, c, n)[on]] = 1e6
    return score


KINDS = [_uniform, _small_integers, _constant, _identical_columns, _banded, _fixed_slots,
         _banded_fixed_duplicated]


def _cases() -> Iterator[tuple[str, npt.NDArray[np.float64]]]:
    rng = np.random.default_rng(20261110)
    for kind in KINDS:
        for r, c in SHAPES:
            batch = kind(rng, PER_KIND_AND_SHAPE, r, c)
            for k, matrix in enumerate(batch):
                # The game maximises a score by negating it; exercise both signs.
                yield f"{kind.__name__} {r}x{c} #{k}", -matrix if k % 4 else matrix
    for size in range(1, 21):  # all-zero and all-equal square and tall matrices
        yield f"zeros {size}x{size}", np.zeros((size, size))
        yield f"ones {size + 3}x{size}", np.ones((size + 3, size))


def test_matches_scipy_on_100k_matrices() -> None:
    count = 0
    for label, matrix in _cases():
        rows, cols = linear_sum_assignment(matrix)
        ref_rows, ref_cols = scipy_lsa(matrix)
        if not (np.array_equal(rows, ref_rows) and np.array_equal(cols, ref_cols)):
            pytest.fail(f"{label}: got {rows.tolist()} -> {cols.tolist()}, SciPy gives "
                        f"{ref_rows.tolist()} -> {ref_cols.tolist()} for\n{matrix!r}")
        count += 1
    assert count == 100_000


@pytest.mark.parametrize("shape", [(11, 11), (30, 11), (11, 30), (0, 0), (0, 5), (5, 0)])
def test_result_arrays_look_like_scipys(shape: tuple[int, int]) -> None:
    matrix = np.random.default_rng(5).random(shape)
    ours, ref = linear_sum_assignment(matrix), scipy_lsa(matrix)
    for mine, theirs in zip(ours, ref, strict=True):
        assert mine.dtype == theirs.dtype == np.int64
        assert mine.shape == theirs.shape
        assert mine.tolist() == theirs.tolist()
    assert ours[0].tolist() == sorted(ours[0].tolist())


def test_maximize_and_other_input_types() -> None:
    rng = np.random.default_rng(6)
    for matrix in (rng.integers(0, 5, (30, 11)), rng.random((8, 12)) < 0.5,
                   rng.random((9, 9)).astype(np.float32), np.asfortranarray(rng.random((6, 4)))):
        for maximize in (False, True):
            ours = linear_sum_assignment(matrix, maximize=maximize)
            ref = scipy_lsa(matrix, maximize=maximize)
            assert ours[0].tolist() == ref[0].tolist()
            assert ours[1].tolist() == ref[1].tolist()


def test_input_is_not_modified() -> None:
    matrix = np.random.default_rng(7).random((30, 11))
    before = matrix.copy()
    linear_sum_assignment(matrix, maximize=True)
    assert np.array_equal(matrix, before)


def test_infeasible_matrix_raises_like_scipy() -> None:
    matrix = np.array([[np.inf, np.inf], [1.0, 2.0]])
    with pytest.raises(ValueError, match="infeasible"):
        scipy_lsa(matrix)
    with pytest.raises(ValueError, match="infeasible"):
        linear_sum_assignment(matrix)
