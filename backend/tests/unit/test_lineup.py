"""Line-up selection: fixing a player in a slot decides who plays there, never how good he is."""

import pytest

from footsim.match.synthetic import synthetic_squad
from footsim.match.teams import BENCH_SIZE
from footsim.world.context import World, get_world


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def test_a_fixed_player_keeps_his_real_slot_rating(world: World) -> None:
    """The user's hand-picked line-up showed every starter as 99 (30 Sep play-test): the score
    that forces a fixed player into his slot was reported as his rating."""
    squad = synthetic_squad(world.defs, 1, 70.0)
    shape = world.defs.formations["4-3-3"]
    auto = world.picker.pick(1, "Club 1", squad, shape)
    # As the tactics screen sends it: every slot fixed, with one substitute swapped in.
    lineup = {sp.slot: sp.player_id for sp in auto.starters if sp.slot is not None}
    lineup[auto.starters[-1].slot or ""] = auto.bench[0].player_id

    sheet = world.picker.pick(1, "Club 1", squad, shape, fixed=lineup)

    assert {sp.slot: sp.player_id for sp in sheet.starters} == lineup
    for sp in sheet.starters:
        real = world.picker.slot_rating(sp.player, sp.position, sp.role)
        assert sp.rating == pytest.approx(min(real, 99.0))
        assert sp.rating < 99.0


def test_the_manager_can_choose_the_bench(world: World) -> None:
    squad = synthetic_squad(world.defs, 1, 70.0)
    shape = world.defs.formations["4-3-3"]
    auto = world.picker.pick(1, "Club 1", squad, shape)
    starters = {sp.slot: sp.player_id for sp in auto.starters if sp.slot is not None}
    started = set(starters.values())
    reserves = [p for p in squad if p.player_id not in started
                and p.player_id not in {sp.player_id for sp in auto.bench}]
    assert reserves  # a squad of more than the eleven and the nine on the bench
    chosen = [reserves[0].player_id, auto.bench[3].player_id]
    lineup = {**starters, "SUB1": chosen[0], "SUB2": chosen[1]}

    sheet = world.picker.pick(1, "Club 1", squad, shape, fixed=lineup)

    assert [sp.player_id for sp in sheet.bench[:2]] == chosen  # in the order he gave
    assert len(sheet.bench) == BENCH_SIZE
    assert len({sp.player_id for sp in sheet.bench}) == BENCH_SIZE
    assert not {sp.player_id for sp in sheet.bench} & started
    assert {sp.slot: sp.player_id for sp in sheet.starters} == starters


def test_an_unavailable_or_starting_substitute_is_replaced_automatically(world: World) -> None:
    squad = synthetic_squad(world.defs, 1, 70.0)
    shape = world.defs.formations["4-3-3"]
    auto = world.picker.pick(1, "Club 1", squad, shape)
    starters = {sp.slot: sp.player_id for sp in auto.starters if sp.slot is not None}
    hurt = auto.bench[0].player
    hurt.available = False
    lineup = {**starters, "SUB1": hurt.player_id, "SUB2": auto.starters[0].player_id}

    sheet = world.picker.pick(1, "Club 1", squad, shape, fixed=lineup)

    assert hurt.player_id not in {sp.player_id for sp in sheet.bench}
    assert len(sheet.bench) == BENCH_SIZE
    assert not {sp.player_id for sp in sheet.bench} & set(starters.values())
    hurt.available = True


def test_a_chosen_bench_without_a_keeper_still_gets_one(world: World) -> None:
    squad = synthetic_squad(world.defs, 1, 70.0)
    shape = world.defs.formations["4-3-3"]
    auto = world.picker.pick(1, "Club 1", squad, shape)
    starters = {sp.slot: sp.player_id for sp in auto.starters if sp.slot is not None}
    outfield = [p for p in squad if p.player_id not in set(starters.values())
                and p.primary_position != "GK"]
    bench = {f"SUB{n + 1}": p.player_id for n, p in enumerate(outfield[:BENCH_SIZE])}
    lineup = {**starters, **bench}
    assert any(p.primary_position == "GK" for p in squad if p.player_id not in starters.values())

    sheet = world.picker.pick(1, "Club 1", squad, shape, fixed=lineup)

    assert any(sp.player.primary_position == "GK" for sp in sheet.bench)


def test_clubs_without_a_chosen_bench_get_the_automatic_one(world: World) -> None:
    squad = synthetic_squad(world.defs, 1, 70.0)
    shape = world.defs.formations["4-3-3"]
    auto = world.picker.pick(1, "Club 1", squad, shape)
    starters = {sp.slot: sp.player_id for sp in auto.starters if sp.slot is not None}
    again = world.picker.pick(1, "Club 1", squad, shape, fixed=starters)
    assert [sp.player_id for sp in again.bench] == [sp.player_id for sp in auto.bench]
