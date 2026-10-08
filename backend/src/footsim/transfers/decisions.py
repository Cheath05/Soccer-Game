"""The transfer market's decisions (W4-4; docs/plans/w3-w4-finances-transfers.md, "Decisions").

These are pure functions, with no database: what a player means to his club, what the club asks
for him, how it answers a bid, how far a buyer goes, the wage a player wants and for how long,
and whether he wants to go. The AI market (world/market.py) and the user's offers (W4-6) both
use them, so everyone deals by the same rules. The numbers are in
data/config/transfers/market.yaml.

Money is in euros here (the database keeps cents).
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from footsim.defs.market import MarketDef
from footsim.transfers.valuation import quote_eur


class Role(StrEnum):
    KEY = "key"
    STARTER = "starter"
    ROTATION = "rotation"
    SURPLUS = "surplus"


def squad_roles(groups: Mapping[str, Sequence[tuple[int, float]]], demand: Mapping[str, int],
                level: float, rules: MarketDef) -> dict[int, Role]:
    """Each player's role at his club. ``groups`` holds each position group's players as
    (id, overall), ``demand`` the formation's slots in each group, and ``level`` the club's level
    (the mean of its starters). In a group, the best ``demand`` players start (a key player when
    more than ``key_margin`` above the level) and the next ``demand`` rotate; the rest are
    surplus. A group the formation doesn't use keeps its best player in rotation."""
    roles: dict[int, Role] = {}
    for group, players in groups.items():
        ranked = sorted(players, key=lambda p: (-p[1], p[0]))
        starting = demand.get(group, 0)
        rotating = starting if starting else 1
        for rank, (player_id, overall) in enumerate(ranked):
            if rank < starting:
                roles[player_id] = (Role.KEY if overall > level + rules.key_margin
                                    else Role.STARTER)
            elif rank < starting + rotating:
                roles[player_id] = Role.ROTATION
            else:
                roles[player_id] = Role.SURPLUS
    return roles


def club_level(starter_overalls: Sequence[float]) -> float:
    """A club's level: the mean overall of its starters."""
    return sum(starter_overalls) / len(starter_overalls) if starter_overalls else 0.0


def _step(table: Sequence[tuple[float, float]], x: float) -> float:
    for limit, value in table:
        if x < limit:
            return value
    return table[-1][1]


def asking_price(value: float, role: Role, years_left: float, listed: bool, distressed: bool,
                 rules: MarketDef) -> int:
    """What a club asks for one of its players: his value, by how much it needs him, how long
    he's under contract, whether it has listed him, and whether it needs the money."""
    price = value * getattr(rules.role_multiplier, role.value)
    price *= _step(rules.contract_multiplier, years_left)
    if listed:
        price *= rules.listed_multiplier
    if distressed:
        price *= rules.distressed_multiplier
    return quote_eur(price)


@dataclass(frozen=True)
class Answer:
    """A club's answer to a bid: ``accept`` (at the bid), ``counter`` (at ``fee``) or
    ``reject``."""

    kind: str
    fee: int


def seller_answer(bid: int, ask: int, rules: MarketDef) -> Answer:
    if bid >= ask:
        return Answer("accept", bid)
    if bid >= rules.counter_from * ask:
        return Answer("counter", ask)
    return Answer("reject", 0)


def opening_bid(value: float, eagerness: float) -> int:
    """A buyer's first bid: the value, scaled by its eagerness (a keyed draw from
    ``bid_eagerness``)."""
    return quote_eur(value * eagerness)


def buyer_ceiling(value: float, urgency: float, rules: MarketDef) -> int:
    """The most a buyer pays for a player: a premium over his value, more when the need is
    urgent (``urgency`` 0 to 1)."""
    premium = rules.max_premium + rules.urgent_premium * min(1.0, max(0.0, urgency))
    return quote_eur(value * premium)


def wage_demand(going_rate: float, current_wage: float | None, free_agent: bool,
                rules: MarketDef) -> int:
    """The weekly wage a player wants to join a club: his new league's going rate for a player of
    his overall, or a raise on what he earns now, whichever is more. A free agent, with no club
    to stay at, settles for less than the going rate."""
    if free_agent or current_wage is None:
        wanted = going_rate * rules.free_agent_discount
    else:
        wanted = max(going_rate, current_wage * rules.move_raise)
    return _wage_steps(wanted)


def _wage_steps(eur: float) -> int:
    """Weekly wages as a club writes them: to €50 below €5K, €500 below €50K, €1K above."""
    step = 50 if eur < 5_000 else 500 if eur < 50_000 else 1_000
    return int(max(step, round(eur / step) * step))


def contract_years(age: float, rules: MarketDef) -> int:
    """How long a new contract runs: longer for the young."""
    for limit, years in rules.contract_years:
        if age <= limit:
            return years
    return rules.contract_years[-1][1]


@dataclass(frozen=True)
class Prospect:
    """What a player weighs up about a move."""

    reputation_step: float  # the buying club's reputation over his own club's
    wage_ratio: float  # the offered wage over his current one
    starts_now: bool
    would_start: bool
    listed: bool
    mood: float  # his own keyed draw, standard normal


def player_utility(prospect: Prospect, rules: MarketDef) -> float:
    weights = rules.answer
    return (weights.reputation * prospect.reputation_step
            + weights.wage * math.log(max(prospect.wage_ratio, 1e-6))
            + weights.starting * (int(prospect.would_start) - int(prospect.starts_now))
            + (weights.listed if prospect.listed else 0.0)
            + weights.noise * prospect.mood)


def player_accepts(prospect: Prospect, rules: MarketDef) -> bool:
    """Whether he wants the move."""
    return player_utility(prospect, rules) >= 0.0


def free_agent_accepts(buyer_reputation: float, own_level: float, rules: MarketDef) -> bool:
    """A free agent takes the wage he asked from any club within ``reach`` of his own level
    (the reputation of a club whose squad is as good as he is): he won't drop far below where
    he belongs."""
    return buyer_reputation >= own_level - rules.reach



@dataclass(frozen=True)
class Haggle:
    """Where talks stand after a bid: ``accept`` (at the bid), ``counter`` (at ``ask``, its last
    word when ``final``), ``reject`` (too low to talk about), or ``ended`` (out of patience)."""

    kind: str
    ask: int
    rounds: int
    final: bool = False


def reservation_price(ask: int, role: Role, listed: bool, distressed: bool,
                      rules: MarketDef) -> int:
    """The lowest a club takes for a player in talks: a share of its asking price by how much
    it needs him (none off for a key player), a little lower if listed or if it needs money."""
    share = getattr(rules.reservation, role.value)
    if listed or distressed:
        share *= rules.reservation_listed
    return quote_eur(ask * share)


def haggle(bid: int, ask: int, reservation: int, rounds: int, rules: MarketDef) -> Haggle:
    """One round of talks over a fee. A bid at the club's current price is accepted. A fair bid
    (at least its walk-away price) brings its price ``concession`` of the way down towards it,
    never below the walk-away price. A bid below that is countered at the same price, and an
    insulting one (below ``insult`` of the price) costs two rounds of patience. After
    ``max_rounds`` the price is final; past it, talks end."""
    if bid >= ask:
        return Haggle("accept", bid, rounds)
    if rounds >= rules.max_rounds:
        return Haggle("ended", ask, rounds, True)
    if bid < rules.insult * ask:
        rounds += 2
        if rounds > rules.max_rounds:
            return Haggle("ended", ask, rounds, True)
        return Haggle("reject", ask, rounds, rounds >= rules.max_rounds)
    rounds += 1
    new_ask = ask
    if bid >= reservation:
        new_ask = max(reservation, quote_eur(ask - rules.concession * (ask - bid)))
    return Haggle("counter", new_ask, rounds, rounds >= rules.max_rounds)
