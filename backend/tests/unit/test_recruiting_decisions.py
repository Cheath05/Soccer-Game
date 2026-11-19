"""High-school recruiting (W9c): how a recruit scores and chooses between programs' offers, on a
hand-built board (no save). Each thing he weighs moves his choice the right way: the money, the
program's prestige against what he expects, his playing time, the distance from home and the
attention he got; a program that can't honour an offer loses him to the next."""

from collections import Counter
from datetime import date

import pytest

from footsim.world.college import recruiting as rc
from footsim.world.context import World, get_world
from footsim.world.meta import CareerMeta

PARTS = ("money", "prestige", "playing_time", "home", "attention")


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def _program(club_id: int, prestige: float = 70.0, state: str = "OH", funding: float = 12.0,
             returning: int = 20, cbs: list[float] | None = None) -> rc.Program:
    p = rc.Program(club_id, f"Program {club_id}", 2, state, prestige, funding, 30.0)
    p.returning_count = returning
    p.returning_money = funding - 4.0
    if cbs:
        p.returning["CB"] = sorted(cbs)
    return p


def _recruit(rid: int = 1, rank: int = 100, state: str | None = "OH",
             overall: float = 45.0) -> rc.Recruit:
    hs = get_world().defs.college.recruiting
    return rc.Recruit(rid, "CB", "CB", state, overall, 55.0, 4, rank,
                      {k: 1.0 for k in PARTS} | {"pace": 1.0}, 0.0, rc.OPEN, None, None,
                      f"Recruit {rid}", rc.along(hs.expectations.prestige, rank),
                      rc.along(hs.expectations.share, rank))


def _board(world: World, programs: list[rc.Program], recruits: list[rc.Recruit],
           user: int | None = None) -> rc.Board:
    meta = CareerMeta(world_seed=7, current_date=date(2026, 10, 5), season_id=1,
                      base_calendar="europe", user_club_id=user, manager_name=None)
    return rc.Board(world, meta, 2, date(2026, 10, 5), {p.club_id: p for p in programs},
                    {r.id: r for r in recruits}, {}, {})


def _best(board: rc.Board, r: rc.Recruit) -> int:
    choices = rc._choices(board, r, rc.starters(board.world))
    return choices[0][1].club_id


def _no_fit(board: rc.Board) -> None:
    for row in board.interest.values():
        row.fit = 0.0


def test_more_money_wins(world: World) -> None:
    a, b = _program(1), _program(2)
    r = _recruit()
    board = _board(world, [a, b], [r])
    board.offer(r.id, 1, 0.25)
    board.offer(r.id, 2, 0.75)
    _no_fit(board)
    assert _best(board, r) == 2


def test_prestige_wins_and_money_is_capped_at_his_hopes(world: World) -> None:
    low, high = _program(1, prestige=45.0), _program(2, prestige=88.0)
    r = _recruit(rank=50)
    board = _board(world, [low, high], [r])
    board.offer(r.id, 1, 1.0)
    board.offer(r.id, 2, 1.0)
    _no_fit(board)
    assert _best(board, r) == 2
    # Money above what he hopes for scores no better.
    parts = rc.parts(board, r, low, 1.0, Counter())
    assert parts["money"] == 1.0
    assert rc.parts(board, r, low, 0.5, Counter())["money"] < 1.0


def test_playing_time_counts_the_players_ahead(world: World) -> None:
    crowded = _program(1, cbs=[60.0, 61.0, 62.0, 63.0])
    open_ = _program(2, cbs=[40.0])
    r = _recruit(overall=50.0)
    board = _board(world, [crowded, open_], [r])
    starters = rc.starters(world)
    assert rc.playing_time(board, r, open_, starters) == 1.0
    assert rc.playing_time(board, r, crowded, starters) < 1.0
    board.offer(r.id, 1, 0.5)
    board.offer(r.id, 2, 0.5)
    _no_fit(board)
    assert _best(board, r) == 2
    # The class already signed counts too: a better centre-back committed to the open program.
    open_.take("CB", 0.5, 58.0)
    open_.take("CB", 0.5, 57.0)
    assert rc.playing_time(board, r, open_, starters) < 1.0


def test_home_is_nearer_and_abroad_is_neutral(world: World) -> None:
    near, far = _program(1, state="OH"), _program(2, state="CA")
    r = _recruit(state="OH")
    board = _board(world, [near, far], [r])
    assert rc.home_score(board, r, near) > 0.9 > rc.home_score(board, r, far)
    board.offer(r.id, 1, 0.5)
    board.offer(r.id, 2, 0.5)
    _no_fit(board)
    assert _best(board, r) == 1
    abroad = _recruit(rid=2, state=None)
    assert rc.home_score(board, abroad, near) == rc.home_score(board, abroad, far)


def test_attention_wins_a_close_call(world: World) -> None:
    a, b = _program(1), _program(2)
    r = _recruit()
    board = _board(world, [a, b], [r])
    board.offer(r.id, 1, 0.5)
    board.offer(r.id, 2, 0.5)
    _no_fit(board)
    board.interest[(r.id, 2)].interest = 80.0
    assert _best(board, r) == 2


def test_he_commits_when_ready_and_clearly_best(world: World) -> None:
    a, b = _program(1, prestige=40.0), _program(2, prestige=85.0)
    r = _recruit(rank=50)
    board = _board(world, [a, b], [r])
    board.offer(r.id, 1, 0.5)
    board.offer(r.id, 2, 0.5)
    _no_fit(board)
    starters = rc.starters(world)
    rc._decide(board, r, starters, now=False, signing=False)
    assert r.status == rc.OPEN  # not ready yet
    r.readiness = 1.0
    rc._decide(board, r, starters, now=False, signing=False)
    assert (r.status, r.club_id) == (rc.COMMITTED, 2)
    assert board.offers[(r.id, 2)].status == rc.ACCEPTED
    assert board.offers[(r.id, 1)].status == rc.DECLINED
    assert b.class_count == 1 and b.class_money == pytest.approx(0.5)


def test_a_program_without_money_or_places_loses_him(world: World) -> None:
    hs = world.defs.college.recruiting
    rich, broke = _program(1, prestige=40.0), _program(2, prestige=85.0)
    broke.returning_money = broke.funding - 0.2  # 0.2 left: can't pay the 0.5 it offered
    r = _recruit(rank=50)
    board = _board(world, [rich, broke], [r])
    board.offer(r.id, 1, 0.5)
    board.offer(r.id, 2, 0.5)
    _no_fit(board)
    r.readiness = 1.0
    rc._decide(board, r, rc.starters(world), now=False, signing=False)
    assert (r.status, r.club_id) == (rc.COMMITTED, 1)
    assert board.offers[(r.id, 2)].status == rc.DECLINED
    full = _program(3, prestige=95.0, returning=hs.programs.roster_max)
    assert not full.can_take(hs, 0.0)


def test_signing_day_signs_commitments_and_the_ready(world: World) -> None:
    a = _program(1)
    committed, open_ = _recruit(1), _recruit(2)
    board = _board(world, [a], [committed, open_])
    board.offer(committed.id, 1, 0.5)
    board.offer(open_.id, 1, 0.5)
    rc._commit(board, committed, a, 0.5, signed=False)
    rc._signing_day(board)
    assert committed.status == rc.SIGNED and committed.signed_on == "2026-10-05"
    assert open_.status == rc.SIGNED and open_.club_id == 1


def test_curves_and_dates(world: World) -> None:
    hs = world.defs.college.recruiting
    assert rc.along([(1, 10.0), (11, 20.0)], 6) == 15.0
    assert rc.along([(1, 10.0), (11, 20.0)], 50) == 20.0
    dates = rc.recruiting_dates(hs, date(2026, 7, 1))
    assert dates.signing_day.weekday() == 2 and dates.signing_day.month == 2
    assert dates.start < dates.signing_day < dates.close
    assert rc.step_down(0.37, 0.05) == pytest.approx(0.35)
    states = hs.states
    assert 2000 < rc.miles(states["NY"], states["CA"]) < 2700
