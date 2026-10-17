"""AI clubs' bids for one another's players (world/market.py, transfers/decisions.py): turned
down, a buyer comes back once with a better offer (market.yaml ai_rebid)."""

from footsim.transfers.decisions import (
    Role,
    asking_price,
    buyer_ceiling,
    opening_bid,
    seller_answer,
)
from footsim.world.context import get_world

VALUE = 10_000_000


def test_a_starter_on_a_long_contract_needs_the_better_offer() -> None:
    rules = get_world().defs.market
    assert rules.ai_rebid
    ask = asking_price(VALUE, Role.STARTER, 4.0, listed=False, distressed=False, rules=rules)
    first = opening_bid(VALUE, 0.95)  # a typical opening bid: below counter_from of the ask
    assert seller_answer(first, ask, rules).kind == "reject"
    better = min(ask, buyer_ceiling(VALUE, 0.4, rules))
    assert seller_answer(better, ask, rules).kind in ("accept", "counter")


def test_a_key_player_still_needs_an_urgent_need() -> None:
    rules = get_world().defs.market
    ask = asking_price(VALUE, Role.KEY, 4.0, listed=False, distressed=False, rules=rules)
    calm = min(ask, buyer_ceiling(VALUE, 0.0, rules))
    urgent = min(ask, buyer_ceiling(VALUE, 1.0, rules))
    assert calm < ask <= urgent  # an improvement alone won't pay a key player's price
