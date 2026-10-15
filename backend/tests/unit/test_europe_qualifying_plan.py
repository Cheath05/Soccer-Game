"""The qualifying plan (W7 A3/A4) on the real access list, without a career: with every one of
the 54 countries filling its places, each round comes out at UEFA's 2026-27 size and each league
phase at 36; an empty holder's place is filled by the best champion in qualifying and the rounds
re-balance around it; and the draw pairs every seeded club with an unseeded one while keeping
clubs of a country, and prohibited pairs, apart."""

from collections import defaultdict

from footsim.world.context import get_world
from footsim.world.europe.common import LEAGUE_PHASE
from footsim.world.europe.places import Vacancy, ordered_places
from footsim.world.europe.qualifying import (
    Entrant,
    Node,
    Plan,
    balance,
    fill_vacancies,
    nodes,
    pair_up,
    sizes,
)

COUNTRIES = 54


def _full_plan(skip: set[tuple[str, str]] = frozenset()) -> Plan:  # type: ignore[assignment]
    """Every place of the access list taken: a club per country and place, its coefficient
    falling with its country's rank (Liechtenstein, 43rd here, has no league places)."""
    world = get_world()
    plan = Plan()
    next_id = 1
    for comp in sorted(world.defs.continental.values(), key=lambda c: c.rank):
        for place in ordered_places(world, comp.key):
            node = Node(comp.key, place.round, None if place.round == LEAGUE_PHASE else place.path)
            if place.holder is not None or place.performance_spot:
                count = 1 if place.holder is not None else 2
                if (comp.key, place.holder or "eps") in skip:
                    continue
                for _ in range(count):
                    plan.direct[node].append(Entrant(next_id, "x", None, 200.0 - next_id / 100))
                    next_id += 1
                continue
            assert place.ranks is not None
            for rank in range(place.ranks[0], min(place.ranks[1], COUNTRIES) + 1):
                if place.cup:
                    count = 1
                elif rank == 43:  # Liechtenstein: a cup, no league
                    continue
                else:
                    assert place.positions is not None
                    count = place.positions[1] - place.positions[0] + 1
                for _ in range(count):
                    plan.direct[node].append(Entrant(next_id, "x", None, 150.0 - rank))
                    next_id += 1
    return plan


def test_every_round_comes_out_at_uefas_size() -> None:
    world = get_world()
    plan = _full_plan()
    balance(world, plan)
    size = sizes(world, plan)
    got = {(n.competition, n.round, n.path): size[n] for n in nodes(world)}
    assert got == {
        ("UCL", "Q1", "champions"): 30, ("UCL", "Q2", "champions"): 24,
        ("UCL", "Q2", "league"): 6, ("UCL", "Q3", "champions"): 12, ("UCL", "Q3", "league"): 8,
        ("UCL", "PO", "champions"): 10, ("UCL", "PO", "league"): 4,
        ("UEL", "Q1", "main"): 16, ("UEL", "Q2", "main"): 16, ("UEL", "Q3", "champions"): 12,
        ("UEL", "Q3", "main"): 14, ("UEL", "PO", "main"): 24,
        ("UECL", "Q1", "main"): 52, ("UECL", "Q2", "champions"): 15, ("UECL", "Q2", "main"): 88,
        ("UECL", "Q3", "champions"): 8, ("UECL", "Q3", "main"): 52,
        ("UECL", "PO", "champions"): 10, ("UECL", "PO", "main"): 38}
    for key, comp in world.defs.continental.items():
        assert size[Node(key, LEAGUE_PHASE, None)] == comp.league_phase.clubs == 36


def test_an_empty_holders_place_goes_to_the_best_champion_in_qualifying() -> None:
    world = get_world()
    plan = _full_plan(skip={("UCL", "UCL")})  # the holders are in through their league
    best = max((e for n in nodes(world) if n.competition == "UCL" and n.path == "champions"
                for e in plan.direct[n]), key=lambda e: e.coefficient)
    fill_vacancies(world, plan, [Vacancy("UCL", LEAGUE_PHASE, None, "champions")])
    balance(world, plan)
    assert best in plan.direct[Node("UCL", LEAGUE_PHASE, None)]
    size = sizes(world, plan)
    assert all(size[Node(k, LEAGUE_PHASE, None)] == 36 for k in world.defs.continental)
    # The champion promoted from the play-off is replaced from below, down to UCL Q1, which
    # sends one more club up to keep its number even: the Conference League's champions path
    # (the UCL Q1 losers) then has a bye a round later, as UEFA's own re-balancing gave in 2026-27.
    odd = [n for n in nodes(world) if size[n] % 2]
    assert len(odd) == 1 and odd[0].competition == "UECL" and odd[0].path == "champions", odd
    assert size[Node("UCL", "Q2", "champions")] == 24 and size[Node("UCL", "Q1", "champions")] == 28


def test_the_draw_keeps_countries_apart() -> None:
    country = {1: "A", 2: "B", 3: "A", 4: "B", 5: "C", 6: "C"}
    seeded, unseeded = [1, 2, 5], [3, 4, 6]
    pairs = pair_up(seeded, unseeded, lambda a, b: country[a] != country[b])
    assert pairs is not None and len(pairs) == 3
    assert all(country[u] != country[s] for u, s in pairs)
    assert pair_up([1], [3], lambda a, b: country[a] != country[b]) is None
    counts: dict[int, int] = defaultdict(int)
    for u, s in pairs:
        counts[u] += 1
        counts[s] += 1
    assert set(counts.values()) == {1}
