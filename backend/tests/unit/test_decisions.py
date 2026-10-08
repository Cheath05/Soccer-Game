"""The transfer market's decisions (W4-4): pure rules, tested alone."""

import pytest

from footsim.defs.market import MarketDef
from footsim.transfers.decisions import (
    Prospect,
    Role,
    asking_price,
    buyer_ceiling,
    club_level,
    contract_years,
    free_agent_accepts,
    haggle,
    opening_bid,
    player_accepts,
    player_utility,
    reservation_price,
    seller_answer,
    squad_roles,
    wage_demand,
)
from footsim.world.context import get_world


def _rules() -> MarketDef:
    return get_world().defs.market


def test_a_club_needs_its_starters_most() -> None:
    rules = _rules()
    groups = {"CB": [(1, 80.0), (2, 74.0), (3, 72.0), (4, 70.0), (5, 60.0)], "GK": [(6, 75.0)],
              "AM": [(7, 71.0), (8, 65.0)]}
    level = club_level([80.0, 74.0, 75.0])
    roles = squad_roles(groups, {"CB": 2, "GK": 1}, level, rules)
    assert roles[1] is Role.KEY  # far above the club's level
    assert roles[2] is Role.STARTER and roles[6] is Role.STARTER
    assert roles[3] is Role.ROTATION and roles[4] is Role.ROTATION
    assert roles[5] is Role.SURPLUS
    # A group the formation doesn't use keeps its best player in rotation.
    assert roles[7] is Role.ROTATION and roles[8] is Role.SURPLUS


def test_the_asking_price_follows_need_contract_and_circumstance() -> None:
    rules = _rules()
    value = 10_000_000
    key = asking_price(value, Role.KEY, 4, False, False, rules)
    starter = asking_price(value, Role.STARTER, 4, False, False, rules)
    surplus = asking_price(value, Role.SURPLUS, 4, False, False, rules)
    assert key > starter > value > surplus
    expiring = asking_price(value, Role.STARTER, 0.5, False, False, rules)
    assert expiring < starter * 0.6  # he could leave for nothing soon
    listed = asking_price(value, Role.STARTER, 4, True, False, rules)
    desperate = asking_price(value, Role.STARTER, 4, True, True, rules)
    assert desperate < listed < starter
    assert starter % 500_000 == 0  # quoted in market steps


def test_a_seller_accepts_counters_or_rejects() -> None:
    rules = _rules()
    ask = 20_000_000
    assert seller_answer(21_000_000, ask, rules).kind == "accept"
    assert seller_answer(21_000_000, ask, rules).fee == 21_000_000
    counter = seller_answer(int(ask * rules.counter_from), ask, rules)
    assert counter.kind == "counter" and counter.fee == ask
    assert seller_answer(int(ask * rules.counter_from) - 1, ask, rules).kind == "reject"


def test_a_buyer_opens_low_and_stretches_for_urgent_needs() -> None:
    rules = _rules()
    value = 8_000_000
    assert opening_bid(value, 0.9) < value
    calm, urgent = buyer_ceiling(value, 0.0, rules), buyer_ceiling(value, 1.0, rules)
    assert value < calm < urgent
    assert buyer_ceiling(value, 5.0, rules) == urgent  # urgency is capped


def test_a_player_wants_a_raise_or_the_going_rate() -> None:
    rules = _rules()
    assert wage_demand(10_000, 5_000, False, rules) == 10_000  # the going rate
    assert wage_demand(10_000, 20_000, False, rules) == round(20_000 * rules.move_raise / 500) * 500
    free = wage_demand(10_000, None, True, rules)
    assert free < 10_000  # a free agent settles for less
    assert wage_demand(1_234, 1_000, False, rules) % 50 == 0


def test_contracts_run_longer_for_the_young() -> None:
    rules = _rules()
    years = [contract_years(age, rules) for age in (18, 23, 24, 27, 29, 31, 33, 36)]
    assert years == sorted(years, reverse=True)
    assert years[0] == 5 and years[-1] == 1


def test_a_player_weighs_club_wage_and_football() -> None:
    rules = _rules()
    step_up = Prospect(reputation_step=15, wage_ratio=1.2, starts_now=True, would_start=True,
                       listed=False, mood=0.0)
    assert player_accepts(step_up, rules)
    step_down = Prospect(reputation_step=-20, wage_ratio=1.15, starts_now=True,
                         would_start=True, listed=False, mood=0.0)
    assert not player_accepts(step_down, rules)
    # Out of favour and listed, he goes down a level to play.
    wanted = Prospect(reputation_step=-5, wage_ratio=1.15, starts_now=False, would_start=True,
                      listed=True, mood=0.0)
    assert player_accepts(wanted, rules)
    # His mood tips a close call either way.
    close = Prospect(reputation_step=-2, wage_ratio=1.15, starts_now=True, would_start=True,
                     listed=False, mood=0.0)
    assert player_utility(close, rules) == pytest.approx(
        rules.answer.reputation * -2 + rules.answer.wage * 0.13976, abs=1e-3)


def test_a_free_agent_wont_drop_far_below_his_level() -> None:
    rules = _rules()
    assert free_agent_accepts(50, 55, rules)
    assert not free_agent_accepts(30, 55, rules)



def test_a_club_gives_ground_to_fair_offers_down_to_its_walk_away_price() -> None:
    rules = _rules()
    ask = 40_000_000
    floor = reservation_price(ask, Role.STARTER, False, False, rules)
    assert floor < ask and reservation_price(ask, Role.KEY, False, False, rules) == ask
    assert reservation_price(ask, Role.SURPLUS, True, False, rules) < reservation_price(
        ask, Role.SURPLUS, False, False, rules)
    # A fair offer brings the price halfway down; repeated, it settles at the floor, then final.
    step = haggle(floor, ask, floor, 0, rules)
    assert step.kind == "counter" and floor <= step.ask < ask and step.rounds == 1
    prices = [step.ask]
    for _ in range(rules.max_rounds - 1):
        step = haggle(floor, step.ask, floor, step.rounds, rules)
        prices.append(step.ask)
    assert prices == sorted(prices, reverse=True) and step.final
    assert haggle(floor, step.ask, floor, step.rounds, rules).kind in ("accept", "ended")
    # Meeting the price is accepted; an insult costs two rounds; patience runs out.
    assert haggle(ask, ask, floor, 0, rules).kind == "accept"
    insult = haggle(int(ask * 0.3), ask, floor, 0, rules)
    assert insult.kind == "reject" and insult.rounds == 2 and insult.ask == ask
    assert haggle(int(ask * 0.3), ask, floor, rules.max_rounds - 1, rules).kind == "ended"
    # Below the floor (but not an insult): countered at the same price.
    low = haggle(int(floor * 0.9), ask, floor, 0, rules)
    assert low.kind == "counter" and low.ask == ask
