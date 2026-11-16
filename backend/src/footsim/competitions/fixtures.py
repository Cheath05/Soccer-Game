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


def split_phases(rounds: list[Round], phases: int) -> list[list[Round]]:
    """A season's rounds cut into ``phases`` equal runs (each phase a round robin)."""
    if phases < 1 or len(rounds) % phases:
        raise ValueError(f"{len(rounds)} rounds don't split into {phases} phases")
    size = len(rounds) // phases
    return [rounds[k * size:(k + 1) * size] for k in range(phases)]



def cross_order(first: Sequence[int], second: Sequence[int],
                rivals: Sequence[tuple[int, int]], rng: np.random.Generator
                ) -> tuple[list[int], list[int]]:
    """The two groups lined up for the cross rounds: shuffled, and with ``rivals`` (pairs, one
    of each group, covering every club) each club facing its rival."""
    if len(first) != len(second):
        raise ValueError("cross rounds need two groups of one size")
    a = list(first)
    rng.shuffle(a)
    if rivals:
        partner = {x: y for x, y in rivals} | {y: x for x, y in rivals}
        if any(c not in partner for c in [*first, *second]):
            raise ValueError("rivals must pair every club")
        return a, [partner[c] for c in a]
    b = list(second)
    rng.shuffle(b)
    return a, b


def cross_rounds(a: Sequence[int], b: Sequence[int], offsets: Sequence[int],
                 swap: bool = False) -> list[Round]:
    """A round per offset: ``a[i]`` meets ``b[i + offset]``, so distinct offsets never repeat a
    pairing. Venues are balanced: with an even number of rounds every club is at home in half
    of them (``balance_venues``); ``swap`` reverses them all (a second phase)."""
    n = len(a)
    rounds = [[(a[i], b[(i + offset) % n]) for i in range(n)] for offset in offsets]
    rounds = balance_venues(rounds)
    return [[(y, x) for x, y in rnd] for rnd in rounds] if swap else rounds


def balance_venues(rounds: list[Round]) -> list[Round]:
    """The same games with venues chosen so each club hosts as many as it visits, or one more
    or fewer when it plays an odd number: the games are walked as closed trails (an Euler
    circuit of each part of the graph, a club of odd degree first) and each game is hosted by
    the club the walk leaves from. Deterministic: clubs and games are taken in order."""
    edges = [(x, y) for rnd in rounds for x, y in rnd]
    adjacency: dict[int, list[int]] = {}
    for k, (x, y) in enumerate(edges):
        adjacency.setdefault(x, []).append(k)
        adjacency.setdefault(y, []).append(k)
    used = [False] * len(edges)
    oriented: list[tuple[int, int]] = list(edges)
    cursor = dict.fromkeys(adjacency, 0)

    def walk(start: int) -> None:
        stack = [start]
        while stack:
            node = stack[-1]
            moved = False
            links = adjacency[node]
            while cursor[node] < len(links):
                k = links[cursor[node]]
                cursor[node] += 1
                if used[k]:
                    continue
                used[k] = True
                x, y = edges[k]
                other = y if x == node else x
                oriented[k] = (node, other)  # the walk leaves ``node``: it hosts
                stack.append(other)
                moved = True
                break
            if not moved:
                stack.pop()

    odd = sorted(c for c, links in adjacency.items() if len(links) % 2)
    for club in odd + sorted(adjacency):
        walk(club)
    out: list[Round] = []
    k = 0
    for rnd in rounds:
        out.append(oriented[k:k + len(rnd)])
        k += len(rnd)
    return out


def grouped_rounds(groups: Sequence[Sequence[int]], legs: int, cross: int,
                   rivals: Sequence[tuple[int, int]], phases: int,
                   rng: np.random.Generator) -> list[list[Round]]:
    """Each phase's rounds for a league of conferences or zones: every group's round robin of
    ``legs`` (a round of each group played together), then ``cross`` rounds against the other
    group, the rivals' first. A later phase plays the round robins again with the venues
    swapped, the rivals again the other way round, and new cross-group opponents. A phase of
    single round robins has its venues balanced as a whole (every club hosts half its games),
    which can leave a pair at the same ground in both phases."""
    robins = [split_phases(round_robin(g, legs * phases, rng), phases) for g in groups]
    order = cross_order(groups[0], groups[1], rivals, rng) if cross else ([], [])
    n = len(order[0])
    out = []
    for phase in range(phases):
        merged = [[game for robin in robins for game in robin[phase][r]]
                  for r in range(len(robins[0][phase]))]
        if cross:
            fresh = cross - 1 if rivals else cross
            offsets = ([0] if rivals else []) + [
                (1 if rivals else 0) + phase * fresh + j for j in range(fresh)]
            if max(offsets) >= n:
                raise ValueError("not enough cross-group opponents for every phase")
            merged += cross_rounds(*order, offsets, swap=phase % 2 == 1)
        if legs == 1:  # an odd group's single round robin hosts unevenly: balance the phase
            merged = balance_venues(merged)
        out.append(merged)
    return out
