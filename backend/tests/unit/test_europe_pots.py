"""The league phase's pots (world/europe/league_phase.py `spread_pots`): coefficient order, no more
than half a pot from one country where it can be helped, and every club in exactly one pot."""

from collections import Counter

from footsim.world.europe.league_phase import spread_pots

SIZE, COUNT = 9, 4


def _country(codes: list[str]) -> dict[int, str]:
    return {club_id: code for club_id, code in enumerate(codes)}


def _check(pots: list[list[int]], ranked: list[int]) -> None:
    assert [len(p) for p in pots] == [SIZE] * COUNT
    assert sorted(c for p in pots for c in p) == sorted(ranked)


def test_a_mixed_field_keeps_coefficient_order() -> None:
    codes = [f"C{k % 12}" for k in range(SIZE * COUNT)]
    ranked = list(range(SIZE * COUNT))
    pots = spread_pots(ranked, SIZE, COUNT, _country(codes))
    assert pots == [ranked[k * SIZE:(k + 1) * SIZE] for k in range(COUNT)]


def test_tied_clubs_from_one_country_are_spread() -> None:
    # Five Polish clubs on their country's floor coefficient, ranked together at the bottom.
    codes = [f"C{k % 12}" for k in range(SIZE * COUNT - 5)] + ["POL"] * 5
    ranked = list(range(SIZE * COUNT))
    pots = spread_pots(ranked, SIZE, COUNT, _country(codes))
    _check(pots, ranked)
    for pot in pots:
        assert max(Counter(codes[c] for c in pot).values()) <= SIZE // 2
    # The one too many moves up to the pot before, swapped with that pot's last club.
    assert Counter(codes[c] for c in pots[2])["POL"] == 1
    assert 26 in pots[3]


def test_a_field_that_cannot_be_spread_keeps_every_club() -> None:
    codes = ["ENG"] * 30 + [f"C{k}" for k in range(6)]
    ranked = list(range(SIZE * COUNT))
    pots = spread_pots(ranked, SIZE, COUNT, _country(codes))
    _check(pots, ranked)
