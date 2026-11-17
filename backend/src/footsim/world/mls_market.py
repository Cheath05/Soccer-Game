"""MLS's roster rules in the market (W9a B4; world/mls.py has the rules themselves).

Every move into an MLS club goes through world/transfers.py or world/loans.py like any other, and
they ask here:
- ``addition_problem``: whether the club would comply with him on that wage. An AI club
  chooses all its designations again, keeping a share of its GAM in reserve; the user's keeps
  theirs and places the newcomer as a club would (the cheapest place that complies). A club
  that doesn't comply can't add anyone until it does. The answer is the rule that blocks it:
  "No international slot free", "All 3 Designated Player slots are full", "Over the salary
  budget by $X after allocation money".
- ``wage_problem``: the same for a renewal's new wage.
- ``fee_split``: a fee's money. Between two MLS clubs it's a trade, paid in GAM (any rest in
  cash, at least $50,000, which the seller gets as GAM). Out of MLS, the seller gets 95% of
  it, as GAM up to $3M a season, the rest in cash. Everywhere else it is the fee, both ways.
- ``filter_renewals``: AI MLS clubs renew only within the rules.

Nothing here touches a move between two clubs outside MLS.
"""

from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from sqlalchemy import Connection, text

from footsim.transfers.valuation import years_old
from footsim.world.context import World
from footsim.world.meta import CareerMeta
from footsim.world.mls import (
    WEEKS,
    Member,
    _club_country,
    _gam,
    _is_ai,
    _secondary_window_start,
    assess,
    choose_designations,
    club_report,
    club_rules,
    figures,
    gam_held,
    load_members,
    mls_club_ids,
    money_for,
    new_problems,
    place_newcomer,
    state,
    under_rules,
)
from footsim.world.squads import display_name


def _newcomer(conn: Connection, world: World, meta: CareerMeta, club_id: int, player_id: int,
              weekly_cents: int, loan: bool, contract_weekly: int | None, day: date) -> Member:
    """A player as he'd be on a club's roster after joining it today."""
    rules = world.defs.mls
    r = conn.execute(text(
        "SELECT p.birth_date, p.first_name, p.last_name, p.known_as, n.code AS nation, "
        "s.homegrown_club_id, COALESCE(s.green_card, 0) AS green_card, s.ga_until_season, "
        "(SELECT 1 FROM contract y WHERE y.person_id = p.id AND y.club_id = :c "
        " AND y.kind = 'youth' LIMIT 1) AS academy "
        "FROM person p LEFT JOIN nation n ON n.id = p.nation_id "
        "LEFT JOIN mls_player s ON s.player_id = p.id WHERE p.id = :p"),
        {"p": player_id, "c": club_id}).one()
    domestic = set(rules.domestic_nations.get(_club_country(conn, world, club_id), []))
    homegrown = bool(r.academy) or r.homegrown_club_id == club_id
    second = _secondary_window_start(conn, world, club_id, meta.season_id)
    age = int(years_old(r.birth_date, day))
    return Member(
        player_id=player_id, name=display_name(r.first_name, r.last_name, r.known_as),
        wage=weekly_cents * WEEKS, age=age, signed_age=age,
        international=not (r.nation in domestic or homegrown or r.green_card),
        canadian=r.nation == "CAN", homegrown=homegrown,
        ga=r.ga_until_season is not None and int(r.ga_until_season) >= meta.season_id,
        late=second is not None and day >= second, loan="in" if loan else None,
        contract_wage=contract_weekly * WEEKS if contract_weekly is not None else None)


def addition_problem(conn: Connection, world: World, meta: CareerMeta, club_id: int,
                     player_id: int, weekly_cents: int, day: date, *, loan: bool = False,
                     contract_weekly: int | None = None, gam_spent: int = 0) -> str | None:
    """Why a player can't join an MLS club today on this wage (``weekly_cents``: what the club
    pays; ``gam_spent``: the GAM it pays for him), or None (also for any club outside MLS)."""
    if not under_rules(conn, club_id, meta.season_id):
        return None
    fig = figures(world)
    money = money_for(world, meta)
    ai = _is_ai(meta, club_id)
    club = club_rules(conn, world, club_id, meta.season_id, gam_spent, reserve=ai)
    members, _ = load_members(conn, world, meta, club_id, day)
    members = [m for m in members if m.player_id != player_id]
    newcomer = _newcomer(conn, world, meta, club_id, player_id, weekly_cents, loan,
                         contract_weekly, day)
    if ai:
        before = assess(fig, club, choose_designations(fig, club, members), money)
        after = assess(fig, club, choose_designations(fig, club, [*members, newcomer]), money)
    else:
        current = club_report(conn, world, meta, club_id, day, money)
        before = assess(fig, club, current.members, money)
        _, after = place_newcomer(fig, club, before.members, newcomer, money)
    if after.compliant:
        return None
    fresh = new_problems(before, after)
    return (fresh or after.problems)[0].refusal + "."


def wage_problem(conn: Connection, world: World, meta: CareerMeta, club_id: int,
                 player_id: int, weekly_cents: int, day: date) -> str | None:
    """Why one of an MLS club's players can't be paid ``weekly_cents`` (a renewal), or None.
    The user's club keeps his designation if it can, else finds him one."""
    if not under_rules(conn, club_id, meta.season_id):
        return None
    fig = figures(world)
    money = money_for(world, meta)
    ai = _is_ai(meta, club_id)
    club = club_rules(conn, world, club_id, meta.season_id, reserve=ai)
    current = club_report(conn, world, meta, club_id, day, money)
    mine = next((m for m in current.members if m.player_id == player_id), None)
    if mine is None:
        return None
    others = [m for m in current.members if m.player_id != player_id]
    raised = replace(mine, wage=weekly_cents * WEEKS if mine.loan is None else mine.wage,
                     contract_wage=None if mine.loan is None else mine.contract_wage)
    before = assess(fig, club, current.members, money)
    if ai:
        after = assess(fig, club, choose_designations(fig, club, [*others, raised]), money)
    else:
        after = assess(fig, club, [*others, raised], money)
        if not after.compliant:
            _, after = place_newcomer(fig, club, others, raised, money)
    if after.compliant:
        return None
    fresh = new_problems(before, after)
    return (fresh or after.problems)[0].refusal + "."


@dataclass(frozen=True)
class FeeSplit:
    """Who pays and gets what for a fee: cash through the ledger, GAM through the clubs'
    seasons. A move outside MLS is all cash both ways."""

    buyer_cash: int
    seller_cash: int
    buyer_gam: int = 0  # GAM the buyer pays
    seller_gam: int = 0  # GAM the seller gets
    refusal: str | None = None


def fee_split(conn: Connection, world: World, meta: CareerMeta, seller: int | None,
              buyer: int | None, fee: int) -> FeeSplit:
    """A fee's money. Between two MLS clubs it's a trade: the buyer pays in GAM, and any rest in
    cash (at least ``trade_min_cash``), all of it GAM for the seller. Out of MLS, the club gets
    ``sale_share`` of it, as GAM up to the season's cap on GAM from sales, the rest as cash."""
    if not fee or seller is None or buyer is None:
        return FeeSplit(fee, fee)
    rules = world.defs.mls
    fig = figures(world)
    selling = under_rules(conn, seller, meta.season_id)
    buying = under_rules(conn, buyer, meta.season_id)
    if selling and buying:
        held = gam_held(conn, buyer, meta.season_id)
        gam = min(held, fee)
        cash = fee - gam
        least = fig.c(rules.trade_min_cash)
        if 0 < cash < least:
            if fee < least:
                return FeeSplit(0, 0, refusal=(
                    "A trade within MLS is paid in GAM: the buyer has "
                    f"{money_for(world, meta)(held)}."))
            cash, gam = least, fee - least
        return FeeSplit(cash, 0, gam, fee)
    if selling:
        row = state(conn, seller, meta.season_id)
        assert row is not None
        club_part = round(fee * rules.sale_share)
        room = max(0, fig.c(rules.gam.from_sales_cap) - int(row.gam_from_sales_cents))
        gam = min(club_part, room)
        return FeeSplit(fee, club_part - gam, 0, gam)
    return FeeSplit(fee, fee)


def apply_fee_gam(conn: Connection, meta: CareerMeta, seller: int, buyer: int, split: FeeSplit,
                  day: date, transfer_id: int) -> None:
    """The GAM of a completed move (after its cash has gone through the ledger)."""
    if split.buyer_gam:
        _gam(conn, meta, buyer, "trade", -split.buyer_gam, day, transfer_id)
    if split.seller_gam:
        kind = "trade" if under_rules(conn, buyer, meta.season_id) else "sale"
        _gam(conn, meta, seller, kind, split.seller_gam, day, transfer_id)
        if kind == "sale":
            conn.execute(text("UPDATE mls_club_season SET gam_from_sales_cents = "
                              "gam_from_sales_cents + :g WHERE club_id = :c AND season_id = :s"),
                         {"g": split.seller_gam, "c": seller, "s": meta.season_id})


def filter_renewals(conn: Connection, world: World, meta: CareerMeta, day: date,
                    renewals: list[dict[str, Any]], leavers: list[tuple[int, int, int]],
                    contract_club: dict[int, tuple[int, int]]
                    ) -> tuple[list[dict[str, Any]], list[tuple[int, int, int]]]:
    """AI MLS clubs renew only within the rules: with the leavers gone and the renewals' new
    wages, a club that wouldn't comply lets its dearest renewals go instead (the most wage for
    the least ability), one by one, until it would. ``renewals``: {id (contract), wage (weekly
    cents), ...}; ``contract_club``: contract id -> (player, club)."""
    from footsim.world.overall_history import player_overalls

    fig = figures(world)
    clubs = mls_club_ids(conn, world, meta.season_id)
    by_club: dict[int, list[dict[str, Any]]] = {}
    for r in renewals:
        _, club_id = contract_club[int(r["id"])]
        if club_id in clubs and club_id != meta.user_club_id and under_rules(
                conn, club_id, meta.season_id):
            by_club.setdefault(club_id, []).append(r)
    if not by_club:
        return renewals, leavers
    leaving = {person for _, person, _ in leavers}
    dropped: set[int] = set()
    for club_id, mine in sorted(by_club.items()):
        club = club_rules(conn, world, club_id, meta.season_id)
        members, _ = load_members(conn, world, meta, club_id, day)
        new_wage = {contract_club[int(r["id"])][0]: int(r["wage"]) * WEEKS for r in mine}
        overall = player_overalls(conn, world, list(new_wage))
        kept = dict(new_wage)
        while kept:
            trial = [replace(m, wage=kept.get(m.player_id, m.wage), contract_wage=None)
                     if m.loan is None else m for m in members if m.player_id not in leaving
                     and (m.player_id in kept or m.player_id not in new_wage)]
            report = assess(fig, club, choose_designations(fig, club, trial))
            if not any(p.code in ("budget", "unbought", "dp", "u22")
                       for p in report.problems):
                break
            worst = max(kept, key=lambda p: (kept[p] / max(1, overall.get(p, 1) ** 4), p))
            del kept[worst]
        dropped |= set(new_wage) - set(kept)
    if not dropped:
        return renewals, leavers
    keep, extra = [], []
    for r in renewals:
        person, club_id = contract_club[int(r["id"])]
        if person in dropped:
            extra.append((int(r["id"]), person, club_id))
        else:
            keep.append(r)
    return keep, leavers + extra
