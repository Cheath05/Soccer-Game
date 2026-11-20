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


def test_the_best_xi_plays_everyone_in_his_best_role(world: World) -> None:
    """"Pick best XI and bench" (college fixes): every slot's role is the one its player rates
    highest in, and the XI with those roles rates at least as high as with the defaults."""
    squad = synthetic_squad(world.defs, 1, 70.0)
    shape = world.defs.formations["4-3-3"]
    roles = world.picker.best_roles(squad, shape)
    assert set(roles) == {s.id for s in shape.slots}
    best = world.picker.pick(1, "Club 1", squad, shape, roles=roles)
    default = world.picker.pick(1, "Club 1", squad, shape)
    assert sum(sp.rating for sp in best.starters) >= sum(sp.rating for sp in default.starters)
    for sp in best.starters:
        group = world.defs.positions[sp.position].group
        options = [r.key for r in world.defs.roles_for(group)]
        assert sp.role in options
        assert world.picker.slot_rating(sp.player, sp.position, sp.role) == pytest.approx(
            max(world.picker.slot_rating(sp.player, sp.position, k) for k in options))
    # The bench knows each player's role overalls, for automatic substitutions.
    assert all(sp.role_overalls for sp in best.bench)


def test_an_automatic_substitute_fits_the_position_in_his_best_role(world: World) -> None:
    """Automatic substitutions (college fixes): whoever on the bench rates highest in the tired
    player's position comes on, in the role he rates highest in there."""
    from footsim.core.rng import derive_rng
    from footsim.match.engine import actions
    from footsim.match.engine.engine import MatchEngine
    from footsim.match.synthetic import synthetic_sheet
    from footsim.match.teams import SheetPlayer
    from footsim.ratings.overall import familiarity_factor

    home = synthetic_sheet(world.defs, world.picker, 1, 70)
    away = synthetic_sheet(world.defs, world.picker, 2, 70)
    eng = MatchEngine(world.defs, home, away, derive_rng(3, "subs"), record=False)
    i = next(int(k) for k in eng.team_indices(0) if eng.position[k] == "CM")
    eng.stamina[:] = 1.0
    eng.stamina[i] = 0.3
    made: list[tuple[int, int, str | None]] = []
    eng.substitute = lambda team, off, on, role=None: made.append((off, on, role))  # type: ignore[method-assign,assignment]
    actions.ai_substitutions(eng, 0)
    assert len(made) == 1 and made[0][0] == eng.players[i].player_id
    _off, on, role = made[0]
    options = [r.key for r in world.defs.roles_for(eng.group[i])]

    def fit(sp: SheetPlayer) -> float:
        return max(sp.role_overalls[k] for k in options) * familiarity_factor(
            sp.player.positions.get("CM", 0))

    pool = [sp for sp in home.bench if sp.position != "GK"]
    chosen = next(sp for sp in pool if sp.player_id == on)
    assert fit(chosen) == pytest.approx(max(fit(sp) for sp in pool))
    assert role == max(options, key=lambda k: chosen.role_overalls[k])
