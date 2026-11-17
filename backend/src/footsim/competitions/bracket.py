"""Fixed single-elimination brackets by seed (a conference tournament, the NCAA tournament).

The field fills the smallest power of two that holds it, in the standard order (1 v 64, 32 v 33,
16 v 49, ...), so the top two seeds can meet only in the final. Seeds the field doesn't reach
are byes: the seed they would have met goes straight to the next round (with 48 teams in 64
places, seeds 1-16). Nothing is reseeded: a match's sides are the winners of the two matches
before it. Seeds are numbers from 1 (the best); a club is whoever holds a seed."""

from collections.abc import Mapping

BYE = 0  # the missing side of a first-round match whose better seed goes through untouched


def rounds_for(entrants: int) -> int:
    """How many rounds a bracket of ``entrants`` has."""
    return max(0, (entrants - 1).bit_length())


def seed_order(size: int) -> list[int]:
    """Seeds 1..``size`` (a power of two) in bracket order, pairs adjacent: for 8, 1 8 4 5 2 7
    3 6."""
    if size < 1 or size & (size - 1):
        raise ValueError(f"a bracket of {size} isn't a power of two")
    order = [1]
    while len(order) < size:
        n = len(order) * 2
        order = [x for s in order for x in (s, n + 1 - s)]
    return order


def matches_in(entrants: int, round_: int) -> int:
    """How many matches (byes included) round ``round_`` (0 the first) has."""
    return (1 << rounds_for(entrants)) >> (round_ + 1)


def first_round(entrants: int) -> list[tuple[int, int]]:
    """The first round's pairs of seeds, the better first; a seed past the field is BYE."""
    order = seed_order(1 << rounds_for(entrants))
    pairs = []
    for a, b in zip(order[::2], order[1::2], strict=True):
        a, b = min(a, b), max(a, b)
        pairs.append((a, b if b <= entrants else BYE))
    return pairs


Winners = Mapping[tuple[int, int], int]  # (round, match) -> the winning seed


def sides(entrants: int, round_: int, index: int, winners: Winners
          ) -> tuple[int | None, int | None]:
    """A match's two seeds, the better first once both are known; None for a side whose match
    isn't decided yet. In the first round the second side may be BYE."""
    if round_ == 0:
        return first_round(entrants)[index]
    a = advanced(entrants, round_ - 1, 2 * index, winners)
    b = advanced(entrants, round_ - 1, 2 * index + 1, winners)
    if a is not None and b is not None and b < a:
        a, b = b, a
    return a, b


def advanced(entrants: int, round_: int, index: int, winners: Winners) -> int | None:
    """The seed that went through from a match: a bye's seed, or its recorded winner."""
    if round_ == 0:
        a, b = first_round(entrants)[index]
        if b == BYE:
            return a
    return winners.get((round_, index))


def champion(entrants: int, winners: Winners) -> int | None:
    """The bracket's winner, once the final is decided."""
    rounds = rounds_for(entrants)
    if rounds == 0:
        return 1 if entrants == 1 else None
    return advanced(entrants, rounds - 1, 0, winners)
