"""What happens to AI clubs' bids and loan requests for the user's players while the game moves
on (Settings → Transfer offers; CareerMeta.offer_mode):
- "stop", the default: Continue and Sim to stop on the day one arrives, as before;
- "wait": they don't stop the game; they wait on the Transfers page until they expire;
- "auto": they are answered as they arrive. A bid at or above the player's asking price (or,
  for a player without one, ``offer_value_pct`` of his value) is accepted; a lower one is
  countered at that price, which the bidder pays only if it's within what it would pay and its
  budget; a player with neither is not for sale and the bid is turned down. Loan requests are
  accepted or turned down as ``offer_loans`` says.
"""

from datetime import date

from sqlalchemy import Connection, text

from footsim.world.context import World
from footsim.world.market import _user_market, answer_bid
from footsim.world.meta import CareerMeta
from footsim.world.money import money_text
from footsim.world.squads import display_name
from footsim.world.transfers import MoveRefused

MODES = ("stop", "wait", "auto")
LOANS = ("accept", "reject")


def stops_for_offers(meta: CareerMeta) -> bool:
    return meta.offer_mode not in ("wait", "auto")


def set_offer_rules(meta: CareerMeta, mode: str, value_pct: int | None, loans: str) -> None:
    if mode not in MODES:
        raise ValueError(f"unknown offer mode {mode}")
    if loans not in LOANS:
        raise ValueError(f"unknown loan answer {loans}")
    if value_pct is not None and not 50 <= value_pct <= 1000:
        raise ValueError("the share of his value must be between 50% and 1000%")
    meta.offer_mode, meta.offer_value_pct, meta.offer_loans = mode, value_pct, loans


def set_asking_price(meta: CareerMeta, player_id: int, fee_eur: int | None) -> None:
    if fee_eur is None:
        meta.asking_prices.pop(player_id, None)
    elif fee_eur <= 0:
        raise ValueError("an asking price must be more than nothing")
    else:
        meta.asking_prices[player_id] = fee_eur


def auto_answer(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """Answer every bid and loan request waiting for the user, by the rules (mode "auto").
    Returns the news of each answer."""
    if meta.offer_mode != "auto" or meta.user_club_id is None:
        return []
    rows = conn.execute(text(
        "SELECT o.id, o.kind, o.player_id, o.fee_cents, pe.first_name, pe.last_name, "
        "pe.known_as, c.name AS bidder FROM transfer_offer o "
        "JOIN person pe ON pe.id = o.player_id JOIN club c ON c.id = o.bidder_club_id "
        "WHERE o.owner_club_id = :u AND o.status = 'pending' AND o.by_user = 0 "
        "AND o.expires >= :d ORDER BY o.id"),
        {"u": meta.user_club_id, "d": day.isoformat()}).all()
    news: list[str] = []
    values: dict[int, float] | None = None
    for r in rows:
        name = display_name(r.first_name, r.last_name, r.known_as)
        if r.kind == "loan":
            result = answer_bid(conn, world, meta, day, r.id, meta.offer_loans)
            news.append(f"{r.bidder} asked to borrow {name}: "
                        + ("you agreed." if result.status == "accepted" else
                           f"turned down ({result.message})" if meta.offer_loans == "accept"
                           else "you said no."))
            continue
        ask = meta.asking_prices.get(r.player_id)
        if ask is None and meta.offer_value_pct is not None:
            if values is None:
                values = _values(conn, world, meta, day)
            value = values.get(r.player_id)
            if value is not None:
                ask = _round(value * meta.offer_value_pct / 100)
        bid = r.fee_cents // 100
        bid_text = money_text(bid, world, meta.currency)
        if ask is None:
            answer_bid(conn, world, meta, day, r.id, "reject")
            news.append(f"{r.bidder} bid {bid_text} for {name}: turned down (not for sale).")
            continue
        ask_text = money_text(ask, world, meta.currency)
        if bid >= ask:
            result = answer_bid(conn, world, meta, day, r.id, "accept")
            news.append(f"{r.bidder} bid {bid_text} for {name}, your price {ask_text}: "
                        + ("sold." if result.status == "accepted"
                           else f"the sale fell through ({result.message})"))
            continue
        result = answer_bid(conn, world, meta, day, r.id, "counter", ask)
        if result.status == "accepted":
            news.append(f"{r.bidder} bid {bid_text} for {name}; you asked for {ask_text} "
                        "and they paid it: sold.")
        elif result.status == "refused":
            news.append(f"{r.bidder} bid {bid_text} for {name}; they'd pay your {ask_text}, "
                        f"but the sale fell through ({result.message})")
        else:
            news.append(f"{r.bidder} bid {bid_text} for {name}; you asked for {ask_text} "
                        "and they walked away.")
    return news


def _values(conn: Connection, world: World, meta: CareerMeta, day: date) -> dict[int, float]:
    """The user's players' values (EUR), as the market sees them today."""
    try:
        market = _user_market(conn, world, meta, day)
    except MoveRefused:
        return {}
    return {int(market.players.ids[k]): float(market.value[k])
            for k in range(len(market.players.ids)) if int(market.owner[k]) == meta.user_club_id}


def _round(fee: float) -> int:
    """A round asking price: two significant figures."""
    if fee < 100:
        return max(1, int(fee))
    step = 10 ** (len(str(int(fee))) - 2)
    return int(round(fee / step) * step)
