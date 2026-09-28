"""Round-robin fixture generation (circle method).

Home/away alternates round by round: in even rounds the top row of the circle is at home,
in odd rounds the bottom row. Each club therefore alternates venues except for about two
"breaks" (consecutive home or away games) per half-season, the theoretical minimum.
Later legs repeat the first half with venues swapped.
"""

from collections.abc import Sequence

import numpy as np

_BYE = -1

Round = list[tuple[int, int]]  # (home club, away club)


def round_robin(club_ids: Sequence[int], legs: int, rng: np.random.Generator) -> list[Round]:
    if len(set(club_ids)) != len(club_ids):
        raise ValueError("duplicate clubs")
    clubs = list(club_ids)
    rng.shuffle(clubs)
    if len(clubs) % 2:
        clubs.append(_BYE)
    n = len(clubs)
    fixed, rotating = clubs[0], clubs[1:]

    first_half: list[Round] = []
    for r in range(n - 1):
        circle = [fixed, *rotating]
        top, bottom = circle[: n // 2], circle[n // 2 :][::-1]
        pairs: Round = []
        for a, b in zip(top, bottom, strict=True):
            if _BYE in (a, b):
                continue
            pairs.append((a, b) if r % 2 == 0 else (b, a))
        first_half.append(pairs)
        rotating = rotating[-1:] + rotating[:-1]

    rounds = list(first_half)
    for leg in range(1, legs):
        swap = leg % 2 == 1
        rounds.extend([[(b, a) if swap else (a, b) for a, b in rnd] for rnd in first_half])
    return rounds
