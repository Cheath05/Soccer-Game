"""The AI transfer market (W4-5; docs/plans/w3-w4-finances-transfers.md, "The AI market").

Every club but the user's buys and sells in its own country's transfer windows, by the rules
in transfers/decisions.py. It moves players through world/transfers.py like everyone else.
- **When:** a club looks at the market every few days of its window, on its own phase, and
  more often in the last week.
- **What for:** needs from its formation (a missing starter, thin cover, a weak or ageing
  starter), most urgent first.
- **Whom:** the best affordable players for the need, anywhere, free agents included, from
  one snapshot of the market a day.
- **How:** the seller's answer, then the player's, then the move.

On its first look in a window a club lists its surplus, and a club in trouble lists its
best-paid spare players. Everything is keyed to the career's seed, so a career run twice trades
the same way. The user's club and players are left out here: W4-6 brings them in, as offers.
"""

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
import numpy.typing as npt
from sqlalchemy import Connection, select, text, update

from footsim.core.rng import derive_rng
from footsim.defs.calendar import DateRange
from footsim.defs.finance import WageLevel
from footsim.defs.formations import FormationDef
from footsim.defs.positions import PositionGroup
from footsim.domain.attributes import ATTRIBUTES
from footsim.persistence.schema import transfer_offer
from footsim.transfers.decisions import (
    Prospect,
    Role,
    asking_price,
    buyer_ceiling,
    club_level,
    contract_years,
    free_agent_accepts,
    opening_bid,
    player_accepts,
    seller_answer,
    squad_roles,
    wage_demand,
)
from footsim.transfers.valuation import values_eur, years_old
from footsim.world.context import AI_FORMATIONS, World
from footsim.world.finance import wage_bills
from footsim.world.loans import Loan, start_loan
from footsim.world.meta import CareerMeta
from footsim.world.squads import display_name
from footsim.world.transfers import Move, MoveRefused, complete_move, fee_text
from footsim.world.windows import club_window_nation, open_window

META_KEY = "market_day"  # the last day the market ran (after_day may run a day twice)
FAMILIAR = 15  # familiarity (0-20) at which a player can play a position
GROUPS = [g.value for g in PositionGroup]
FREE = -1  # the owner of a free agent


# --- what changes only monthly: ratings and positions -----------------------------------


@dataclass
class _Players:
    """Every active player's ratings and positions (they change on the 1st of the month)."""

    ids: npt.NDArray[np.int64]
    index: dict[int, int]
    in_group: dict[str, npt.NDArray[np.float64]]  # his overall in each position group
    can_play: dict[str, npt.NDArray[np.bool_]]  # familiar with a position in the group
    primary: npt.NDArray[np.str_]  # his best position's group
    overall: npt.NDArray[np.float64]  # in his best position's group
    birth: list[str]
    premium: npt.NDArray[np.float64]
    reputation: npt.NDArray[np.float64]


_CACHE: dict[tuple[Any, ...], _Players] = {}


def _players(conn: Connection, world: World, meta: CareerMeta, day: date) -> _Players:
    count, top = conn.execute(text(
        "SELECT COUNT(*), MAX(person_id) FROM player WHERE retired_on IS NULL")).one()
    key = (str(conn.engine.url), meta.seed, meta.season_id, day.year, day.month, count, top)
    if key in _CACHE:
        return _CACHE[key]
    rows = conn.execute(text(
        "SELECT p.person_id AS id, pe.birth_date AS birth, p.reputation AS reputation, "
        "COALESCE(p.value_premium, 0) AS premium, a.* FROM player p "
        "JOIN person pe ON pe.id = p.person_id JOIN player_attr a ON a.player_id = p.person_id "
        "WHERE p.retired_on IS NULL ORDER BY p.person_id")).all()
    ids = np.array([r.id for r in rows], dtype=np.int64)
    index = {int(i): n for n, i in enumerate(ids)}
    attrs = np.array([[getattr(r, a) for a in ATTRIBUTES] for r in rows], dtype=float)
    by_group = world.model.group_overalls(attrs)
    in_group = {g.value: np.asarray(by_group[g], dtype=float) for g in PositionGroup}
    can_play = {g: np.zeros(len(ids), dtype=bool) for g in GROUPS}
    best: dict[int, tuple[int, str]] = {}
    for r in conn.execute(text("SELECT player_id, position, familiarity FROM player_position "
                               "ORDER BY player_id, position")):
        n = index.get(int(r.player_id))
        if n is None:
            continue
        group = world.defs.positions[r.position].group.value
        if r.familiarity >= FAMILIAR:
            can_play[group][n] = True
        if r.player_id not in best or r.familiarity > best[r.player_id][0]:
            best[r.player_id] = (r.familiarity, group)
    primary = np.array([best.get(int(i), (0, "CM"))[1] for i in ids])
    for n, g in enumerate(primary):
        can_play[str(g)][n] = True
    overall = np.array([in_group[str(g)][n] for n, g in enumerate(primary)], dtype=float)
    players = _Players(ids, index, in_group, can_play, primary, np.round(overall),
                       [r.birth for r in rows], np.array([r.premium for r in rows], dtype=float),
                       np.array([r.reputation for r in rows], dtype=float))
    _CACHE.clear()
    _CACHE[key] = players
    return players


# --- clubs ----------------------------------------------------------------------------


@dataclass
class _Club:
    id: int
    reputation: float
    nation: str
    league: str | None  # its league's key this season; None outside the game's leagues
    wage_level: WageLevel
    formation: FormationDef
    budget: int  # euros, for fees and new wages this season
    balance: int
    bill: int  # weekly wages, euros
    capacity: int  # the weekly wages its income supports, euros
    signed: int = 0  # this window
    sold: int = 0

    @property
    def distressed(self) -> bool:
        return self.balance < 0 or self.bill > 1.2 * self.capacity


@dataclass
class _Need:
    group: str
    kind: str  # short | upgrade | depth | succession | improve
    urgency: float
    low: float  # the overall wanted, in the group
    high: float
    beat: float  # the overall to beat (the starter he'd replace), or 0
    max_age: float


@dataclass
class _View:
    """A club's squad, as the market sees it on the day."""

    rows: list[int]
    starters: dict[str, list[int]]
    level: float
    roles: dict[int, Role]
    cover: dict[str, int] = field(default_factory=dict)


class _Market:
    def __init__(self, conn: Connection, world: World, meta: CareerMeta, day: date,
                 season_end: date) -> None:
        self.conn, self.world, self.meta, self.day = conn, world, meta, day
        self.rules = world.defs.market
        self.season_end = season_end
        self.weeks_left = max(1.0, (season_end - day).days / 7)
        self.players = _players(conn, world, meta, day)
        p = self.players
        n = len(p.ids)
        self.owner = np.full(n, FREE, dtype=np.int64)
        self.wage = np.zeros(n, dtype=np.int64)  # euros a week (a free agent's last)
        self.years_left = np.zeros(n, dtype=float)
        self.listed = np.zeros(n, dtype=bool)
        self.moved = np.zeros(n, dtype=bool)
        self.plays_for = np.full(n, FREE, dtype=np.int64)  # where he plays (on loan: there)
        self.on_loan = np.zeros(n, dtype=bool)
        for r in conn.execute(text(
                "SELECT person_id, club_id, wage_weekly_cents, end_date, listed FROM contract "
                "WHERE is_active = 1 AND kind != 'loan'")):
            k = p.index.get(int(r.person_id))
            if k is None:
                continue
            self.owner[k] = r.club_id
            self.wage[k] = r.wage_weekly_cents // 100
            self.years_left[k] = max(0.0, (date.fromisoformat(r.end_date) - day).days / 365.25)
            self.listed[k] = bool(r.listed)
        for r in conn.execute(text(
                "SELECT person_id, wage_weekly_cents FROM contract k WHERE is_active = 0 "
                "AND NOT EXISTS (SELECT 1 FROM contract a WHERE a.person_id = k.person_id "
                "AND a.is_active = 1) ORDER BY end_date, id")):
            k = p.index.get(int(r.person_id))
            if k is not None:
                self.wage[k] = r.wage_weekly_cents // 100  # the last one wins
        since = (day - timedelta(days=self.rules.moved_rest_days)).isoformat()
        for (pid,) in conn.execute(text("SELECT player_id FROM transfer WHERE date > :d"),
                                   {"d": since}):
            k = p.index.get(int(pid))
            if k is not None:
                self.moved[k] = True
        self.age = np.array([years_old(b, day) for b in p.birth], dtype=float)
        self.clubs = self._load_clubs()
        # His market's reputation: his club's, or a free agent's own.
        self.market_rep = np.array([self.clubs[int(o)].reputation if int(o) in self.clubs
                                    else p.reputation[k] for k, o in enumerate(self.owner)])
        self.value = values_eur(world.defs.valuation, p.overall, self.age, p.primary == "GK",
                                self.market_rep, p.premium).astype(np.int64)
        for r in conn.execute(text("SELECT person_id, club_id, kind FROM playing")):
            k = p.index.get(int(r.person_id))
            if k is not None:
                self.plays_for[k] = r.club_id
                self.on_loan[k] = r.kind == "loan"
        # A squad, as needs and roles see it, is who plays there (W4-8).
        self.by_club: dict[int, set[int]] = {}
        for k, o in enumerate(self.plays_for):
            if o != FREE:
                self.by_club.setdefault(int(o), set()).add(k)
        self.views: dict[int, _View] = {}

    # --- loading -----------------------------------------------------------------------

    def _load_clubs(self) -> dict[int, _Club]:
        world, season = self.world, self.meta.season_id
        leagues = {int(r.club_id): str(r.key) for r in self.conn.execute(text(
            "SELECT m.club_id, c.key FROM club_league_membership m JOIN competition c "
            "ON c.id = m.competition_id WHERE m.season_id = :s"), {"s": season})}
        formations = {int(r.club_id): str(r.formation) for r in self.conn.execute(text(
            "SELECT club_id, formation FROM tactic"))}
        bills = {club: bill // 100 for club, bill in wage_bills(self.conn).items()}
        clubs = {}
        for r in self.conn.execute(text(
                "SELECT c.id, c.reputation, c.source_league, n.code AS nation, "
                "f.transfer_budget_cents AS budget, f.balance_cents AS balance, "
                "f.wage_budget_cents AS capacity FROM club c "
                "JOIN club_finance f ON f.club_id = c.id LEFT JOIN nation n ON n.id = c.nation_id "
                "ORDER BY c.id")):
            league = leagues.get(int(r.id))
            source = (world.defs.leagues[league].source_leagues[:1] if league else []) or [
                r.source_league or ""]
            formation = world.defs.formations.get(formations.get(int(r.id), AI_FORMATIONS[-1]))
            clubs[int(r.id)] = _Club(
                id=int(r.id), reputation=float(r.reputation),
                nation=world.defs.leagues[league].nation if league else str(r.nation or ""),
                league=league, wage_level=world.defs.wage_levels.for_league(source[0]),
                formation=formation or world.defs.formations[AI_FORMATIONS[-1]],
                budget=int(r.budget) // 100, balance=int(r.balance) // 100,
                bill=bills.get(int(r.id), 0), capacity=int(r.capacity) // 100)
        return clubs

    def counts(self, club: _Club, window: DateRange) -> None:
        signed, sold = self.conn.execute(text(
            "SELECT SUM(to_club_id = :c), SUM(from_club_id = :c) FROM transfer "
            "WHERE date >= :d AND kind IN ('transfer', 'free')"),
            {"c": club.id, "d": window.start.isoformat()}).one()
        club.signed, club.sold = int(signed or 0), int(sold or 0)

    # --- a squad as the market sees it ---------------------------------------------------

    def demand(self, club: _Club) -> dict[str, int]:
        result: dict[str, int] = {}
        for slot in club.formation.slots:
            group = self.world.defs.positions[slot.position].group.value
            result[group] = result.get(group, 0) + 1
        return result

    def view(self, club: _Club) -> _View:
        if club.id in self.views:
            return self.views[club.id]
        p = self.players
        rows = sorted(self.by_club.get(club.id, set()), key=lambda k: int(p.ids[k]))
        demand = self.demand(club)
        taken: set[int] = set()
        starters: dict[str, list[int]] = {}
        for group in GROUPS:  # keepers first, then back to front
            able = [k for k in rows if k not in taken and p.can_play[group][k]]
            able.sort(key=lambda k: (-p.in_group[group][k], int(p.ids[k])))
            starters[group] = able[:demand.get(group, 0)]
            taken.update(starters[group])
        level = club_level([float(p.in_group[g][k]) for g, ks in starters.items() for k in ks])
        lists: dict[str, list[tuple[int, float]]] = {}
        home = {k: g for g, ks in starters.items() for k in ks}
        for k in rows:
            group = home.get(k, str(p.primary[k]))
            lists.setdefault(group, []).append((int(p.ids[k]), float(p.in_group[group][k])))
        by_id = squad_roles(lists, demand, level, self.rules)
        roles = {k: by_id[int(p.ids[k])] for k in rows}
        cover = {g: sum(1 for k in rows if k not in taken and p.can_play[g][k]) for g in GROUPS}
        result = _View(rows, starters, level, roles, cover)
        self.views[club.id] = result
        return result

    def needs(self, club: _Club) -> list[_Need]:
        p, rules = self.players, self.rules
        view = self.view(club)
        demand = self.demand(club)
        result = []
        for group in GROUPS:
            wanted = demand.get(group, 0)
            if not wanted:
                continue
            starters = view.starters[group]
            up_low, up_high = view.level + rules.upgrade_band[0], view.level + rules.upgrade_band[1]
            if len(starters) < wanted:
                result.append(_Need(group, "short", 1.0, up_low - rules.weak_gap, up_high, 0.0,
                                    33.0))
                continue
            weakest = min(float(p.in_group[group][k]) for k in starters)
            if weakest < view.level - rules.weak_gap:
                result.append(_Need(group, "upgrade", min(1.0, (view.level - weakest) / 10),
                                    max(up_low - rules.weak_gap, weakest + rules.min_improvement),
                                    up_high, weakest, 31.0))
            spare = (rules.keepers_wanted - 1 if group == "GK"
                     else wanted * (rules.depth_per_slot - 1))
            if view.cover.get(group, 0) < spare and len(view.rows) < rules.squad_max:
                result.append(_Need(group, "depth", 0.3 + 0.1 * (spare - view.cover[group]),
                                    view.level + rules.depth_band[0],
                                    view.level + rules.depth_band[1], 0.0, 33.0))
            for k in starters:
                if self.age[k] < rules.ageing_from:
                    continue
                heir = any(self.age[j] < 30 and p.can_play[group][j]
                           and p.in_group[group][j] >= p.in_group[group][k] - 3
                           for j in view.rows if j != k)
                if not heir:
                    result.append(_Need(group, "succession", 0.25, up_low - rules.weak_gap,
                                        up_high, 0.0, 27.0))
                    break
        if club.budget > 0 and not any(n.kind in ("short", "upgrade") for n in result):
            # Nothing is missing: a club with money to spend still looks to improve its
            # weakest starter (ambition, not need).
            weakest_group, weakest = min(
                ((g, min(float(p.in_group[g][k]) for k in view.starters[g]))
                 for g in GROUPS if view.starters.get(g)), key=lambda gw: gw[1] - view.level)
            result.append(_Need(weakest_group, "improve", rules.improve_urgency,
                                weakest + rules.min_improvement,
                                view.level + rules.upgrade_band[1], weakest, 30.0))
        return sorted(result, key=lambda n: (-n.urgency, GROUPS.index(n.group)))

    # --- buying ---------------------------------------------------------------------------

    def going_rate(self, club: _Club, overall: float) -> float:
        return max(self.world.defs.wage_levels.minimum_weekly_wage,
                   club.wage_level.wage_for(overall))

    def candidates(self, club: _Club, need: _Need, user_club: int | None) -> list[int]:
        p, rules = self.players, self.rules
        rating = p.in_group[need.group]
        mask = (p.can_play[need.group] & (self.owner != club.id) & ~self.moved & ~self.on_loan
                & (rating >= need.low) & (rating <= need.high) & (self.age <= need.max_age))
        if need.beat:
            mask &= rating >= need.beat + rules.min_improvement
        rows = np.nonzero(mask)[0]
        if not len(rows):
            return []
        reachable = (self.owner[rows] == FREE) | self.listed[rows] | (
            self.market_rep[rows] <= club.reputation + rules.reach)
        rows = rows[reachable]
        if not len(rows):
            return []
        free = self.owner[rows] == FREE
        fee = np.where(free, 0.0, self.value[rows] * np.where(self.listed[rows], 0.9, 1.25))
        level = club.wage_level
        going = np.maximum(self.world.defs.wage_levels.minimum_weekly_wage,
                           level.reference_wage * level.per_point ** (
                               p.overall[rows] - level.reference_overall))
        wage = np.where(free, going * rules.free_agent_discount,
                        np.maximum(going, self.wage[rows] * rules.move_raise))
        cost = fee + wage * self.weeks_left
        share = 1.0 if need.kind == "short" else rules.max_deal_share
        affordable = ((cost <= club.budget * share)
                      & (wage <= club.capacity * rules.max_wage_share))
        if need.kind != "short":
            affordable &= club.bill + wage <= club.capacity * (1 + rules.wage_slack)
        rows, cost, free = rows[affordable], cost[affordable], free[affordable]
        if not len(rows):
            return []
        score = (rating[rows] - (need.beat or need.low) + 0.3 * np.maximum(0.0, 24 - self.age[rows])
                 - 4.0 * cost / max(club.budget, 1) + np.where(free & (need.kind == "depth"), 2.0,
                                                               0.0))
        order = sorted(range(len(rows)), key=lambda i: (-score[i], int(p.ids[rows[i]])))
        return [int(rows[i]) for i in order[:rules.candidates_per_need]]

    def attempt(self, club: _Club, need: _Need, k: int, window: DateRange) -> str | None:
        """Try to sign the player at row ``k`` for ``need``. Returns the news, or None."""
        p, rules, meta = self.players, self.rules, self.meta
        player_id = int(p.ids[k])
        owner = int(self.owner[k])
        going = self.going_rate(club, float(p.overall[k]))
        if owner == FREE:
            level = self.world.defs.world_build.reputation
            own_level = level.club_base + level.club_per_point * (
                float(p.overall[k]) - level.club_reference_overall)
            if not free_agent_accepts(club.reputation, own_level, rules):
                return None
            fee = 0
            wage = wage_demand(going, None, True, rules)
        elif owner == meta.user_club_id:
            return self.bid_for_user(club, need, k, window)
        else:
            seller = self.clubs.get(owner)
            if seller is None or seller.sold >= rules.max_out:
                return None
            role = self.view(seller).roles.get(k, Role.SURPLUS)
            ask = asking_price(float(self.value[k]), role, float(self.years_left[k]),
                               bool(self.listed[k]), seller.distressed, rules)
            eagerness = derive_rng(meta.seed, "market-bid", self.day.isoformat(), club.id,
                                   player_id).uniform(*rules.bid_eagerness)
            bid = opening_bid(float(self.value[k]), eagerness)
            answer = seller_answer(bid, ask, rules)
            if answer.kind == "reject":
                return None
            fee = answer.fee
            if fee > buyer_ceiling(float(self.value[k]), need.urgency, rules):
                return None
            wage = wage_demand(going, float(self.wage[k]), False, rules)
            mood = derive_rng(meta.seed, "market-mood", player_id, club.id,
                              window.start.isoformat()).normal()
            prospect = Prospect(
                reputation_step=club.reputation - seller.reputation,
                wage_ratio=wage / max(float(self.wage[k]), 1.0),
                starts_now=role in (Role.KEY, Role.STARTER),
                would_start=need.kind in ("short", "upgrade", "succession", "improve"),
                listed=bool(self.listed[k]), mood=float(mood))
            if not player_accepts(prospect, rules):
                return None
        if wage > club.capacity * rules.max_wage_share:
            return None
        if fee + wage * self.weeks_left > club.budget:
            return None
        years = contract_years(float(self.age[k]), rules)
        first = self.season_end.year if (self.season_end - self.day).days > 30 else (
            self.season_end.year + 1)
        move = Move(player_id, club.id, fee * 100, wage * 100, date(first + years - 1, 6, 30))
        try:
            complete_move(self.conn, self.world, meta, move, self.day)
        except MoveRefused:
            return None
        self._moved(k, club, owner, wage, years)
        return ""  # AI clubs' deals stay out of the user's news (the history has them)

    def loan_end(self) -> date:
        """A loan runs to the end of the season (next season's, in the summer window's June)."""
        year = self.season_end.year if (self.season_end - self.day).days > 30 else (
            self.season_end.year + 1)
        return date(year, 6, 30)

    def loan_candidates(self, club: _Club, need: _Need) -> list[int]:
        """Young players at clubs well above this one who'd cover the need (their clubs decide
        whether they're spare)."""
        p, rules = self.players, self.rules
        rating = p.in_group[need.group]
        mask = (p.can_play[need.group] & (self.owner != club.id) & (self.owner != FREE)
                & ~self.moved & ~self.on_loan & (self.age <= rules.loan_max_age)
                & (rating >= need.low) & (rating <= need.high + 2)
                & (self.market_rep >= club.reputation + rules.loan_level_gap))
        rows = np.nonzero(mask)[0]
        order = sorted(rows, key=lambda k: (-rating[k], int(p.ids[k])))
        return [int(k) for k in order[:rules.candidates_per_need]]

    def attempt_loan(self, club: _Club, k: int, window: DateRange) -> str | None:
        """Try to borrow the player at row ``k``: his club lends only a player it has spare (a
        loan offer if he's the user's). Returns the news ("" for none), or None."""
        p, rules, meta = self.players, self.rules, self.meta
        player_id, owner = int(p.ids[k]), int(self.owner[k])
        parent = self.clubs.get(owner)
        if parent is None:
            return None
        if owner == meta.user_club_id:
            return self.loan_offer_for_user(club, k, window)
        if self.view(parent).roles.get(k, Role.SURPLUS) is not Role.SURPLUS:
            return None
        try:
            start_loan(self.conn, self.world, meta,
                       Loan(player_id, club.id, self.loan_end(), rules.loan_share), self.day)
        except MoveRefused:
            return None
        self.on_loan[k], self.moved[k] = True, True
        self.by_club.get(int(self.plays_for[k]), set()).discard(k)
        self.plays_for[k] = club.id
        self.by_club.setdefault(club.id, set()).add(k)
        club.signed += 1
        self._refresh_money(club)
        self.views.pop(club.id, None)
        self.views.pop(owner, None)
        return ""

    def loan_offer_for_user(self, club: _Club, k: int, window: DateRange) -> str | None:
        """An AI club asks to borrow one of the user's young players: an offer like a bid."""
        p, rules, meta = self.players, self.rules, self.meta
        player_id = int(p.ids[k])
        made = self.conn.execute(text(
            "SELECT SUM(status = 'pending') AS waiting, COUNT(*) AS window, "
            "SUM(player_id = :p AND bidder_club_id = :c) AS again FROM transfer_offer "
            "WHERE owner_club_id = :u AND by_user = 0 AND created >= :start"),
            {"p": player_id, "c": club.id, "u": meta.user_club_id,
             "start": window.start.isoformat()}).one()
        if ((made.waiting or 0) >= rules.max_bids_for_user or made.window >= rules.bids_per_window
                or made.again):
            return None
        share = round(rules.loan_share * float(self.wage[k])) * 100
        self.conn.execute(transfer_offer.insert().values(
            player_id=player_id, bidder_club_id=club.id, owner_club_id=meta.user_club_id,
            kind="loan", status="pending", fee_cents=0, counter_fee_cents=None,
            wage_weekly_cents=share, years=None, created=self.day.isoformat(),
            expires=(self.day + timedelta(days=rules.offer_days)).isoformat(), by_user=0))
        names = self.conn.execute(text(
            "SELECT pe.first_name, pe.last_name, pe.known_as, c.name FROM person pe, club c "
            "WHERE pe.id = :p AND c.id = :c"), {"p": player_id, "c": club.id}).one()
        name = display_name(names.first_name, names.last_name, names.known_as)
        return (f"{names.name} want {name} on loan until the end of the season. Answer them on "
                "the Transfers page.")

    def bid_for_user(self, club: _Club, need: _Need, k: int, window: DateRange) -> str | None:
        """An AI club wants one of the user's players: it doesn't buy him, it makes an offer
        that stands ``offer_days`` and stops sim-to-date. Returns the news, or None."""
        p, rules, meta = self.players, self.rules, self.meta
        player_id = int(p.ids[k])
        # Bids are an event, not a stream: a few a window, and a club turned down for a player
        # doesn't come back for him in the same window.
        made = self.conn.execute(text(
            "SELECT SUM(status = 'pending') AS waiting, COUNT(*) AS window, "
            "SUM(player_id = :p AND bidder_club_id = :c) AS again FROM transfer_offer "
            "WHERE owner_club_id = :u AND by_user = 0 AND created >= :start"),
            {"p": player_id, "c": club.id, "u": meta.user_club_id,
             "start": window.start.isoformat()}).one()
        if ((made.waiting or 0) >= rules.max_bids_for_user or made.window >= rules.bids_per_window
                or made.again):
            return None
        user = self.clubs[int(self.owner[k])]
        role = self.view(user).roles.get(k, Role.SURPLUS)
        eagerness = derive_rng(meta.seed, "market-bid", self.day.isoformat(), club.id,
                               player_id).uniform(*rules.bid_eagerness)
        value = float(self.value[k])
        fee = min(opening_bid(value, eagerness * (1 + 0.2 * need.urgency)),
                  buyer_ceiling(value, need.urgency, rules))
        wage = wage_demand(self.going_rate(club, float(p.overall[k])), float(self.wage[k]),
                           False, rules)
        if (wage > club.capacity * rules.max_wage_share
                or fee + wage * self.weeks_left > club.budget):
            return None
        mood = derive_rng(meta.seed, "market-mood", player_id, club.id,
                          window.start.isoformat()).normal()
        if not player_accepts(Prospect(
                reputation_step=club.reputation - user.reputation,
                wage_ratio=wage / max(float(self.wage[k]), 1.0),
                starts_now=role in (Role.KEY, Role.STARTER), would_start=True,
                listed=bool(self.listed[k]), mood=float(mood)), rules):
            return None
        self.conn.execute(transfer_offer.insert().values(
            player_id=player_id, bidder_club_id=club.id, owner_club_id=user.id, kind="transfer",
            status="pending", fee_cents=fee * 100, counter_fee_cents=None,
            wage_weekly_cents=wage * 100, years=contract_years(float(self.age[k]), rules),
            created=self.day.isoformat(),
            expires=(self.day + timedelta(days=rules.offer_days)).isoformat(), by_user=0))
        names = self.conn.execute(text(
            "SELECT pe.first_name, pe.last_name, pe.known_as, c.name FROM person pe, club c "
            "WHERE pe.id = :p AND c.id = :c"), {"p": player_id, "c": club.id}).one()
        name = display_name(names.first_name, names.last_name, names.known_as)
        return (f"{names.name} bid {fee_text(fee * 100)} for {name}. Answer them on the "
                "Transfers page.")

    def _moved(self, k: int, club: _Club, seller_id: int, wage: int, years: int) -> None:
        old_wage = int(self.wage[k])
        self.owner[k], self.wage[k], self.years_left[k] = club.id, wage, years
        self.market_rep[k] = club.reputation
        self.plays_for[k] = club.id
        self.listed[k], self.moved[k] = False, True
        self.by_club.setdefault(club.id, set()).add(k)
        club.signed += 1
        club.bill += wage
        self._refresh_money(club)
        self.views.pop(club.id, None)
        if seller_id != FREE and seller_id in self.clubs:
            seller = self.clubs[seller_id]
            self.by_club[seller_id].discard(k)
            seller.sold += 1
            seller.bill -= old_wage
            self._refresh_money(seller)
            self.views.pop(seller_id, None)

    def _refresh_money(self, club: _Club) -> None:
        r = self.conn.execute(text(
            "SELECT transfer_budget_cents AS budget, balance_cents AS balance FROM club_finance "
            "WHERE club_id = :c"), {"c": club.id}).one()
        club.budget, club.balance = int(r.budget) // 100, int(r.balance) // 100

    # --- selling --------------------------------------------------------------------------

    def list_players(self, club: _Club) -> None:
        """A club's first look in a window: it lists its surplus, its old players who no longer
        make the team, and, in trouble, its best-paid spare players."""
        p, rules = self.players, self.rules
        view = self.view(club)
        for k in view.rows:
            self.listed[k] = False
        surplus = sorted((k for k in view.rows if view.roles[k] is Role.SURPLUS),
                         key=lambda k: (p.overall[k], int(p.ids[k])))
        chosen = set(surplus[:max(0, len(view.rows) - rules.squad_max)])
        chosen.update(k for k in view.rows if self.age[k] >= 31
                      and view.roles[k] in (Role.ROTATION, Role.SURPLUS)
                      and p.overall[k] < view.level - 5)
        if club.distressed:
            spare = sorted((k for k in view.rows if view.roles[k] is not Role.KEY),
                           key=lambda k: (-self.wage[k], int(p.ids[k])))
            chosen.update(spare[:2])
        self.conn.execute(text(
            "UPDATE contract SET listed = 0 WHERE club_id = :c AND is_active = 1 "
            "AND kind != 'loan'"), {"c": club.id})
        if chosen:
            self.conn.execute(text(
                "UPDATE contract SET listed = 1 WHERE person_id = :p AND is_active = 1 "
                "AND kind != 'loan'"), [{"p": int(p.ids[k])} for k in sorted(chosen)])
            for k in chosen:
                self.listed[k] = True


# --- the day ------------------------------------------------------------------------------


def _ran_on(conn: Connection) -> str | None:
    row = conn.execute(text("SELECT value FROM game_meta WHERE key = :k"), {"k": META_KEY}).first()
    return json.loads(row.value) if row else None


def _mark(conn: Connection, day: date) -> None:
    conn.execute(text("INSERT INTO game_meta (key, value) VALUES (:k, :v) "
                      "ON CONFLICT(key) DO UPDATE SET value = excluded.value"),
                 {"k": META_KEY, "v": json.dumps(day.isoformat())})


def _acts(world: World, meta: CareerMeta, club: _Club, window: DateRange, day: date) -> bool:
    rules = world.defs.market
    since, left = (day - window.start).days, (window.end - day).days
    rng = derive_rng(meta.seed, "market-day", day.isoformat(), club.id)
    acts = (since + club.id) % rules.interval_days == 0 or (
        left < rules.deadline_days and rng.random() < rules.deadline_activity)
    if acts and club.league is None:
        acts = rng.random() < rules.outside_league_activity
    return acts


def run_market(conn: Connection, world: World, meta: CareerMeta, day: date,
               season_end: date) -> list[str]:
    """One day of the AI market (at most once a day). Returns the day's notable deals."""
    if _ran_on(conn) == day.isoformat():
        return []
    nations = {c.nation for c in world.defs.calendars.values()}
    windows = {n: open_window(world, n, meta.season_id, day) for n in sorted(nations)}
    if not any(windows.values()):
        return []
    _mark(conn, day)
    conn.execute(text("UPDATE transfer_offer SET status = 'expired' WHERE status = 'pending' "
                      "AND expires < :d"), {"d": day.isoformat()})
    market = _Market(conn, world, meta, day, season_end)
    default = world.defs.market.default_window_nation
    acting = []
    for club in market.clubs.values():
        if club.id == meta.user_club_id:
            continue
        window = windows.get(club.nation) if club.nation in windows else windows.get(default)
        if window is not None and _acts(world, meta, club, window, day):
            acting.append((club, window))
    acting.sort(key=lambda cw: (-cw[0].reputation, cw[0].id))
    news: list[tuple[int, str]] = []
    for club, window in acting:
        market.counts(club, window)
        if (day - window.start).days < world.defs.market.interval_days:
            market.list_players(club)
        limit = (world.defs.market.max_in_summer if window.start.month in (5, 6, 7, 8, 9)
                 else world.defs.market.max_in_winter)
        for need in market.needs(club)[:world.defs.market.needs_per_day]:
            if club.signed >= limit:
                break
            # Cover first looks for a loan of a young player who'd play more here.
            options = ([("loan", k) for k in market.loan_candidates(club, need)]
                       if need.kind in ("depth", "short") else [])
            options += [("buy", k) for k in market.candidates(club, need, meta.user_club_id)]
            for how, k in options:
                story = (market.attempt_loan(club, k, window) if how == "loan"
                         else market.attempt(club, need, k, window))
                if story is None:
                    continue
                if story:  # only what concerns the user's club: a bid for one of their players
                    news.append((0, story))
                break
    news.sort(key=lambda n: n[0])
    return [text_ for _, text_ in news[:world.defs.market.max_news] if text_]



# --- the user's side (W4-6): the same rules, asked for by the user ------------------------


@dataclass(frozen=True)
class Terms:
    """What it would take to sign a player now, as the user's club sees it."""

    player_id: int
    club_id: int | None  # his club; None for a free agent
    value_eur: int
    wage_eur: int  # the weekly wage he'd ask of the user's club
    years: int  # the contract he'd sign
    listed: bool
    window_open: bool  # the user's club's window


@dataclass(frozen=True)
class OfferResult:
    """The answer to the user's offer: ``accepted`` (done: ``news`` says so), ``countered``
    (the club wants ``fee_eur``), ``rejected`` (by the club or the player: ``message`` says
    who and why), or ``refused`` (against the rules: the window, the budget, the squad)."""

    status: str
    message: str
    fee_eur: int = 0
    wage_eur: int = 0
    years: int = 0


def _user_market(conn: Connection, world: World, meta: CareerMeta, day: date) -> _Market:
    if meta.user_club_id is None:
        raise MoveRefused("Watching only: there's no club of your own.")
    end = season_calendar_end(world, meta)
    return _Market(conn, world, meta, day, end)


def season_calendar_end(world: World, meta: CareerMeta) -> date:
    from footsim.world.season import season_calendar

    return season_calendar(world, meta, meta.season_id).season_end


def _contract_end(market: _Market, years: int) -> date:
    first = market.season_end.year if (market.season_end - market.day).days > 30 else (
        market.season_end.year + 1)
    return date(first + years - 1, 6, 30)


def _user_view(market: _Market, k: int) -> tuple[_Club, int, float]:
    """The user's club, his row and the ask of the user's club (the going rate in its league)."""
    assert market.meta.user_club_id is not None
    club = market.clubs[market.meta.user_club_id]
    return club, k, market.going_rate(club, float(market.players.overall[k]))


def player_terms(conn: Connection, world: World, meta: CareerMeta, day: date,
                 player_id: int) -> Terms:
    market = _user_market(conn, world, meta, day)
    k = market.players.index.get(player_id)
    if k is None:
        raise MoveRefused("No such player.")
    club, _, going = _user_view(market, k)
    owner = int(market.owner[k])
    free = owner == FREE
    wage = wage_demand(going, None if free else float(market.wage[k]), free, market.rules)
    nation = club_window_nation(conn, club.id, meta.season_id)
    return Terms(player_id, None if free else owner, int(market.value[k]), wage,
                 contract_years(float(market.age[k]), market.rules), bool(market.listed[k]),
                 open_window(world, nation, meta.season_id, day) is not None)


def make_offer(conn: Connection, world: World, meta: CareerMeta, day: date, player_id: int,
               fee_eur: int, wage_eur: int | None = None, years: int | None = None
               ) -> OfferResult:
    """The user's offer for a player, answered at once: his club's answer (the asking price,
    as any club would ask), then his (the same weighing as for any move), then the move."""
    market = _user_market(conn, world, meta, day)
    rules = market.rules
    k = market.players.index.get(player_id)
    if k is None:
        return OfferResult("refused", "No such player.")
    club, _, going = _user_view(market, k)
    owner = int(market.owner[k])
    if owner == club.id:
        return OfferResult("refused", "He's already yours.")
    nation = club_window_nation(conn, club.id, meta.season_id)
    if open_window(world, nation, meta.season_id, day) is None:
        return OfferResult("refused", "The transfer window is closed.")
    value = float(market.value[k])
    if fee_eur > club.budget:
        return OfferResult("refused", "That's beyond the budget.")
    if owner == FREE:
        if fee_eur:
            return OfferResult("refused", "A free agent costs no fee.")
        level = world.defs.world_build.reputation
        own_level = level.club_base + level.club_per_point * (
            float(market.players.overall[k]) - level.club_reference_overall)
        if not free_agent_accepts(club.reputation, own_level, rules):
            return OfferResult("rejected", "He doesn't want to join a club at your level.")
        asked = wage_demand(going, None, True, rules)
    else:
        seller = market.clubs[owner]
        role = market.view(seller).roles.get(k, Role.SURPLUS)
        ask = asking_price(value, role, float(market.years_left[k]), bool(market.listed[k]),
                           seller.distressed, rules)
        answer = seller_answer(fee_eur, ask, rules)
        if answer.kind == "reject":
            return OfferResult("rejected", "They turned it down: it's well short of what they "
                               "want.")
        if answer.kind == "counter":
            # Amounts go as numbers: the page shows them in the user's currency.
            return OfferResult("countered", "They want more for him.", fee_eur=ask)
        asked = wage_demand(going, float(market.wage[k]), False, rules)
        group = str(market.players.primary[k])
        starters = market.view(club).starters.get(group, [])
        weakest = min((float(market.players.in_group[group][j]) for j in starters), default=0.0)
        window = open_window(world, nation, meta.season_id, day)
        assert window is not None
        mood = derive_rng(meta.seed, "market-mood", player_id, club.id,
                          window.start.isoformat()).normal()
        wanted = wage_eur if wage_eur is not None else asked
        if not player_accepts(Prospect(
                reputation_step=club.reputation - seller.reputation,
                wage_ratio=wanted / max(float(market.wage[k]), 1.0),
                starts_now=role in (Role.KEY, Role.STARTER),
                would_start=float(market.players.in_group[group][k]) >= weakest,
                listed=bool(market.listed[k]), mood=float(mood)), rules):
            return OfferResult("rejected", "He doesn't want to move to your club.")
    wage = wage_eur if wage_eur is not None else asked
    if wage < asked:
        return OfferResult("rejected", "He wants a higher wage.",
                           wage_eur=asked)
    length = years or contract_years(float(market.age[k]), rules)
    move = Move(player_id, club.id, fee_eur * 100, wage * 100, _contract_end(market, length),
                by_user=True)
    try:
        news = complete_move(conn, world, meta, move, day)
    except MoveRefused as exc:
        return OfferResult("refused", str(exc))
    return OfferResult("accepted", news[0], fee_eur, wage, length)


def answer_bid(conn: Connection, world: World, meta: CareerMeta, day: date, offer_id: int,
               action: str, fee_eur: int | None = None) -> OfferResult:
    """The user's answer to an AI club's bid for one of their players: ``accept`` (he goes),
    ``reject``, or ``counter`` at ``fee_eur`` (the bidder pays it if it's within what it would
    pay for him and its budget, and walks away otherwise)."""
    row = conn.execute(select(transfer_offer).where(transfer_offer.c.id == offer_id)).first()
    if (row is None or row.owner_club_id != meta.user_club_id or row.status != "pending"
            or row.by_user):
        return OfferResult("refused", "That offer isn't open.")
    if action == "reject":
        conn.execute(update(transfer_offer).where(transfer_offer.c.id == offer_id)
                     .values(status="rejected"))
        return OfferResult("rejected", "You turned it down.")
    if row.kind == "loan":
        return _answer_loan_offer(conn, world, meta, day, row, action)
    fee = row.fee_cents // 100
    if action == "counter":
        if fee_eur is None:
            return OfferResult("refused", "Say what you want for him.")
        market = _user_market(conn, world, meta, day)
        k = market.players.index[row.player_id]
        bidder = market.clubs[row.bidder_club_id]
        ceiling = buyer_ceiling(float(market.value[k]), 0.5, market.rules)
        wage = row.wage_weekly_cents // 100
        if fee_eur > ceiling or fee_eur + wage * market.weeks_left > bidder.budget:
            conn.execute(update(transfer_offer).where(transfer_offer.c.id == offer_id)
                         .values(status="withdrawn", counter_fee_cents=fee_eur * 100))
            return OfferResult("rejected", "They won't pay that, and have walked away.")
        fee = fee_eur
    elif action != "accept":
        return OfferResult("refused", f"Unknown answer {action}.")
    market = _user_market(conn, world, meta, day)
    move = Move(row.player_id, row.bidder_club_id, fee * 100, row.wage_weekly_cents,
                _contract_end(market, row.years or 1), by_user=True)
    try:
        news = complete_move(conn, world, meta, move, day)
    except MoveRefused as exc:
        conn.execute(update(transfer_offer).where(transfer_offer.c.id == offer_id)
                     .values(status="failed"))
        return OfferResult("refused", str(exc))
    conn.execute(update(transfer_offer).where(transfer_offer.c.id == offer_id)
                 .values(status="accepted", counter_fee_cents=fee * 100))
    return OfferResult("accepted", news[0], fee, row.wage_weekly_cents // 100, row.years or 1)


def bid_arrived(conn: Connection, meta: CareerMeta, day: date) -> bool:
    """Whether an AI club bid for one of the user's players on ``day`` (sim-to-date stops)."""
    if meta.user_club_id is None:
        return False
    return conn.execute(text(
        "SELECT 1 FROM transfer_offer WHERE owner_club_id = :u AND status = 'pending' "
        "AND by_user = 0 AND created = :d LIMIT 1"),
        {"u": meta.user_club_id, "d": day.isoformat()}).first() is not None



def _answer_loan_offer(conn: Connection, world: World, meta: CareerMeta, day: date,
                       row: Any, action: str) -> OfferResult:
    """The user's answer to an AI club asking to borrow one of their players."""
    if action == "counter":
        return OfferResult("refused", "A loan is accepted or turned down.")
    if action != "accept":
        return OfferResult("refused", f"Unknown answer {action}.")
    market = _user_market(conn, world, meta, day)
    owner = conn.execute(text("SELECT wage_weekly_cents FROM contract WHERE person_id = :p AND "
                              "is_active = 1 AND kind != 'loan'"), {"p": row.player_id}).first()
    share = row.wage_weekly_cents / owner.wage_weekly_cents if owner and owner.wage_weekly_cents \
        else market.rules.loan_share
    try:
        news = start_loan(conn, world, meta, Loan(row.player_id, row.bidder_club_id,
                                                  market.loan_end(), min(1.0, share)), day)
    except MoveRefused as exc:
        conn.execute(update(transfer_offer).where(transfer_offer.c.id == row.id)
                     .values(status="failed"))
        return OfferResult("refused", str(exc))
    conn.execute(update(transfer_offer).where(transfer_offer.c.id == row.id)
                 .values(status="accepted"))
    return OfferResult("accepted", news)


def make_loan_offer(conn: Connection, world: World, meta: CareerMeta, day: date,
                    player_id: int, share: float) -> OfferResult:
    """The user asks to borrow a player until the season's end, paying ``share`` of his wage:
    his club lends a spare player (a rotation player only for most of his wage; never a
    starter), and he goes where he'll play."""
    market = _user_market(conn, world, meta, day)
    rules = market.rules
    k = market.players.index.get(player_id)
    if k is None:
        return OfferResult("refused", "No such player.")
    club = market.clubs[meta.user_club_id] if meta.user_club_id is not None else None
    assert club is not None
    owner = int(market.owner[k])
    if owner == FREE:
        return OfferResult("refused", "He's a free agent: sign him instead.")
    if owner == club.id:
        return OfferResult("refused", "He's already yours.")
    parent = market.clubs[owner]
    role = market.view(parent).roles.get(k, Role.SURPLUS)
    if role in (Role.KEY, Role.STARTER):
        return OfferResult("rejected", f"{_club_name(conn, owner)} won't loan out a first-team "
                                       "player.")
    if market.age[k] > rules.loan_max_age + 2 and not market.listed[k]:
        return OfferResult("rejected", f"{_club_name(conn, owner)} don't loan out their senior "
                                       "players.")
    if role is Role.ROTATION and share < 0.75:
        return OfferResult("rejected", "They'd want you to pay at least 75% of his wage.")
    window = open_window(world, club_window_nation(conn, club.id, meta.season_id),
                         meta.season_id, day)
    if window is None:
        return OfferResult("refused", "The transfer window is closed.")
    mood = derive_rng(meta.seed, "market-mood", player_id, club.id,
                      window.start.isoformat()).normal()
    if not player_accepts(Prospect(reputation_step=club.reputation - parent.reputation,
                                   wage_ratio=1.0, starts_now=False, would_start=True,
                                   listed=bool(market.listed[k]), mood=float(mood)), rules):
        return OfferResult("rejected", "He doesn't want to go on loan to your club.")
    try:
        news = start_loan(conn, world, meta, Loan(player_id, club.id, market.loan_end(),
                                                  share, by_user=True), day)
    except MoveRefused as exc:
        return OfferResult("refused", str(exc))
    return OfferResult("accepted", news)


def _club_name(conn: Connection, club_id: int) -> str:
    return str(conn.execute(text("SELECT name FROM club WHERE id = :c"), {"c": club_id}
                            ).scalar_one())
