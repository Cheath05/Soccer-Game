"""Contracts running out (W4-7; docs/plans/w3-w4-finances-transfers.md, "Contracts and loans").

At each rollover, contracts that end with the season are settled:
- An AI club renews the players still in its plans: key players, starters and rotation players
  up to their age limits, and young surplus players with the potential to grow into the side.
  The new wage and length come from transfers/decisions.py, as for a signing. A key player
  whose level is well above his club's may refuse and leave.
- The user's club keeps only those the user renewed during the season (``renew``). The rest
  leave on 30 June, as in real football. News reminds the user on 1 April, 1 May and 1 June.

Everyone who isn't renewed becomes a free agent: his contract ends, and a history row of kind
``expired`` records it. The market can sign him, and an unsigned free agent is likelier to
leave the game (world/lifecycle.py). Nothing here is random except through the career's seed.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Connection, text

from footsim.core.rng import derive_rng
from footsim.transfers.decisions import (
    Prospect,
    Role,
    contract_years,
    player_accepts,
    wage_demand,
)
from footsim.world.context import World
from footsim.world.finance import signing_cost_cents, weeks_left
from footsim.world.market import FREE, _Market
from footsim.world.meta import CareerMeta
from footsim.world.squads import display_name

KEY_AGE_LIMIT = 35  # a key player is kept up to this age
AGE_LIMIT = 33  # other starters and rotation players up to this one
YOUNG = 21  # a surplus player this young is kept when his potential is above the club's level
REMINDERS = {(4, 1), (5, 1), (6, 1)}  # (month, day) the user hears about expiring contracts


@dataclass(frozen=True)
class Expiring:
    """One of the user's players whose contract ends with the season, and his terms to stay."""

    player_id: int
    name: str
    age: int
    overall: int
    end_date: str
    wage_eur: int  # now, a week
    asks_eur: int  # to stay, a week
    years: int
    willing: bool  # whether he'd sign at all


def _expiring_rows(conn: Connection, season_end: date, club_id: int | None = None
                   ) -> list[tuple[int, int, int, str]]:
    """Active non-loan contracts ending by ``season_end``: (contract id, person, club, end)."""
    where = "AND club_id = :c" if club_id is not None else ""
    return [(int(r.id), int(r.person_id), int(r.club_id), str(r.end_date)) for r in conn.execute(
        text(f"SELECT id, person_id, club_id, end_date FROM contract WHERE is_active = 1 "
             f"AND kind != 'loan' AND end_date <= :e {where} ORDER BY id"),
        {"e": season_end.isoformat(), "c": club_id})]


def _terms(market: _Market, club_id: int, k: int) -> tuple[int, int, bool]:
    """What a player asks to stay at his club: (weekly wage, years, willing)."""
    rules = market.rules
    club = market.clubs[club_id]
    going = market.going_rate(club, float(market.players.overall[k]))
    asks = wage_demand(going, float(market.wage[k]), False, rules)
    years = contract_years(float(market.age[k]), rules)
    role = market.view(club).roles.get(k, Role.SURPLUS)
    level = market.world.defs.world_build.reputation
    own_level = level.club_base + level.club_per_point * (
        float(market.players.overall[k]) - level.club_reference_overall)
    willing = True
    if role is Role.KEY and own_level - club.reputation > rules.reach:
        mood = derive_rng(market.meta.seed, "renewal", int(market.players.ids[k]),
                          market.meta.season_id).normal()
        willing = player_accepts(Prospect(
            reputation_step=club.reputation - own_level, wage_ratio=asks / max(
                float(market.wage[k]), 1.0), starts_now=True, would_start=True, listed=False,
            mood=float(mood)), rules)
    return asks, years, willing


def _keeps(market: _Market, club_id: int, k: int) -> bool:
    """Whether an AI club wants to keep a player whose contract is ending."""
    view = market.view(market.clubs[club_id])
    role = view.roles.get(k, Role.SURPLUS)
    age = float(market.age[k])
    if role is Role.KEY:
        return age <= KEY_AGE_LIMIT
    if role in (Role.STARTER, Role.ROTATION):
        return age <= AGE_LIMIT
    pid = int(market.players.ids[k])
    potential: int = market.conn.execute(text("SELECT pa_hidden FROM player WHERE person_id = :p"),
                                    {"p": pid}).scalar_one()
    return age <= YOUNG and potential > view.level


def settle_expiring(conn: Connection, world: World, meta: CareerMeta, last_day: date,
                    new_season_end: date) -> list[str]:
    """At the rollover (``last_day`` is the old season's last): AI clubs renew whom they want;
    everyone else whose contract ends now leaves as a free agent. Returns the user's news."""
    old_end = last_day
    rows = _expiring_rows(conn, old_end)
    if not rows:
        return []
    market = _Market(conn, world, meta, last_day, old_end)
    news: list[str] = []
    renewals, leavers = [], []
    for contract_id, person, club_id, _ in rows:
        k = market.players.index.get(person)
        if k is None or int(market.owner[k]) == FREE:
            continue
        if club_id != meta.user_club_id and club_id in market.clubs and _keeps(market, club_id, k):
            asks, years, willing = _terms(market, club_id, k)
            if willing:
                end = date(new_season_end.year + years - 1, 6, 30)
                renewals.append({"id": contract_id, "end": end.isoformat(), "wage": asks * 100})
                continue
        leavers.append((contract_id, person, club_id))
    leavers, kept = _keep_a_squad(conn, world, market, leavers, new_season_end, renewals)
    news += kept
    if renewals:
        conn.execute(text("UPDATE contract SET end_date = :end, wage_weekly_cents = :wage "
                          "WHERE id = :id"), renewals)
    for contract_id, person, club_id in leavers:
        conn.execute(text("UPDATE contract SET is_active = 0, listed = 0 WHERE id = :id"),
                     {"id": contract_id})
        conn.execute(text(
            "INSERT INTO transfer (player_id, from_club_id, to_club_id, date, season_id, kind, "
            "fee_cents, wage_weekly_cents, contract_end, by_user) VALUES (:p, :c, NULL, :d, :s, "
            "'expired', 0, 0, NULL, :u)"),
            {"p": person, "c": club_id, "d": old_end.isoformat(), "s": meta.season_id,
             "u": int(club_id == meta.user_club_id)})
        if club_id == meta.user_club_id:
            who = conn.execute(text("SELECT first_name, last_name, known_as FROM person "
                                    "WHERE id = :p"), {"p": person}).one()
            news.append(f"{display_name(who.first_name, who.last_name, who.known_as)} leaves "
                        "as his contract runs out.")
    return news


def _keep_a_squad(conn: Connection, world: World, market: _Market,
                  leavers: list[tuple[int, int, int]], new_season_end: date,
                  renewals: list[dict[str, object]]) -> tuple[list[tuple[int, int, int]],
                                                             list[str]]:
    """No club is left unable to field a side: where the leavers would take a club below the
    senior floor (``user_min_players``), its best leavers stay on one-year deals at the wage they
    ask until it's back at the floor. Returns the leavers who still go, and the user's news."""
    floor = world.defs.lifecycle.squads.user_min_players
    by_club: dict[int, list[tuple[int, int, int]]] = {}
    for leaver in leavers:
        by_club.setdefault(leaver[2], []).append(leaver)
    end = date(new_season_end.year, 6, 30).isoformat()
    going, news = [], []
    for club_id, club_leavers in sorted(by_club.items()):
        seniors = int(conn.execute(text(
            "SELECT COUNT(*) FROM contract WHERE club_id = :c AND is_active = 1 "
            "AND kind = 'player'"), {"c": club_id}).scalar_one())
        leaving_seniors = int(conn.execute(text(
            "SELECT COUNT(*) FROM contract WHERE id IN (" + ", ".join(
                str(c) for c, _, _ in club_leavers) + ") AND kind = 'player'")).scalar_one())
        short = floor - (seniors - leaving_seniors)
        ranked = sorted(club_leavers, key=lambda lv: (
            -float(market.players.overall[market.players.index[lv[1]]])
            if lv[1] in market.players.index else 0.0, lv[1]))
        for contract_id, person, _ in ranked:
            k = market.players.index.get(person)
            if short > 0 and k is not None and club_id in market.clubs:
                asks, _, _ = _terms(market, club_id, k)
                renewals.append({"id": contract_id, "end": end, "wage": asks * 100})
                short -= 1
                if club_id == market.meta.user_club_id:
                    who = conn.execute(text("SELECT first_name, last_name, known_as FROM person "
                                            "WHERE id = :p"), {"p": person}).one()
                    news.append(f"{display_name(who.first_name, who.last_name, who.known_as)} "
                                "signs on for another year: the squad needed the numbers.")
                continue
            going.append((contract_id, person, club_id))
    return going, news


def expiring_for_user(conn: Connection, world: World, meta: CareerMeta, day: date,
                      season_end: date) -> list[Expiring]:
    """The user's players whose contracts end with this season, and what each asks to stay."""
    if meta.user_club_id is None:
        return []
    rows = _expiring_rows(conn, season_end, meta.user_club_id)
    if not rows:
        return []
    market = _Market(conn, world, meta, day, season_end)
    result = []
    for _, person, _, end in rows:
        k = market.players.index.get(person)
        if k is None:
            continue
        asks, years, willing = _terms(market, meta.user_club_id, k)
        who = conn.execute(text("SELECT first_name, last_name, known_as FROM person "
                                "WHERE id = :p"), {"p": person}).one()
        result.append(Expiring(person, display_name(who.first_name, who.last_name, who.known_as),
                               int(market.age[k]), int(market.players.overall[k]), end,
                               int(market.wage[k]), asks, years, willing))
    return sorted(result, key=lambda e: (-e.overall, e.player_id))


class RenewalRefused(Exception):
    """Why a renewal can't happen (shown to the user)."""


def renew(conn: Connection, world: World, meta: CareerMeta, day: date, season_end: date,
          player_id: int, wage_eur: int | None = None, years: int | None = None) -> str:
    """The user renews one of their players whose contract is ending: at the wage he asks (or
    more), for the length he asks (or another, 1 to 5 years). The raise counts against this
    season's budget for the weeks left. Returns the news."""
    mine = [e for e in expiring_for_user(conn, world, meta, day, season_end)
            if e.player_id == player_id]
    if not mine:
        raise RenewalRefused("His contract isn't ending this season.")
    terms = mine[0]
    if not terms.willing:
        raise RenewalRefused(f"{terms.name} won't sign a new contract with you.")
    wage = terms.asks_eur if wage_eur is None else wage_eur
    if wage < terms.asks_eur:
        raise RenewalRefused(f"{terms.name} wants at least {terms.asks_eur:,} a week (EUR).")
    length = years or terms.years
    if not 1 <= length <= 5:
        raise RenewalRefused("A contract runs 1 to 5 years.")
    raise_cents = max(0, wage - terms.wage_eur) * 100
    cost = signing_cost_cents(0, raise_cents, weeks_left(conn, meta.season_id, day))
    budget = int(conn.execute(text("SELECT transfer_budget_cents FROM club_finance "
                                   "WHERE club_id = :c"), {"c": meta.user_club_id}).scalar_one())
    if cost > budget:
        raise RenewalRefused("That's beyond the budget.")
    end = date(season_end.year + length, 6, 30)
    conn.execute(text(
        "UPDATE contract SET end_date = :end, wage_weekly_cents = :wage WHERE person_id = :p "
        "AND club_id = :c AND is_active = 1 AND kind != 'loan'"),
        {"end": end.isoformat(), "wage": wage * 100, "p": player_id, "c": meta.user_club_id})
    if cost:
        conn.execute(text("UPDATE club_finance SET transfer_budget_cents = "
                          "transfer_budget_cents - :c WHERE club_id = :u"),
                     {"c": cost, "u": meta.user_club_id})
    return f"{terms.name} signs a new contract to {end.year}."


def contract_reminders(conn: Connection, world: World, meta: CareerMeta, day: date,
                       season_end: date) -> list[str]:
    """On 1 April, 1 May and 1 June: the user's players whose contracts are about to end."""
    if (day.month, day.day) not in REMINDERS or meta.user_club_id is None:
        return []
    count = len(_expiring_rows(conn, season_end, meta.user_club_id))
    if not count:
        return []
    days = (season_end - day).days
    return [f"{count} of your players' contracts end in {days} days. Renew the ones you want on "
            "the Transfers page (Contracts); the others leave on 30 June."]

