"""MLS's roster rules (W9a B3-B4; docs/plans/w9a-americas.md, data/config/rules/mls.yaml).

Every player at an MLS club has a **roster designation** (senior, supplemental, DP, U22,
homegrown, Generation adidas) and sits on the Senior Roster (slots 1-20) or the Supplemental
Roster (21-30). His **budget charge** follows from his yearly wage and his designation:
- a senior player is charged his wage; a Designated Player a fixed charge by age (half if signed
  after the secondary window opened); a U22 Initiative player $150,000 or $200,000;
- the Supplemental Roster isn't charged; each empty senior slot below 18 is charged the senior
  minimum;
- **TAM, then GAM, buy down** the charges of players paid above the maximum, as a club would:
  first what each needs to come down to the maximum, then, while the club is over its budget,
  TAM down to its floor for players paid up to TAM's ceiling, then GAM by up to half.

A club is **compliant** when its charges after buy-downs fit the budget, its rosters fit their
slots (the Supplemental Roster's two tiers too), its Designated and U22 players fit its roster
model, its internationals fit its international slots, and its players earn MLS's minimums.

The first half of this module is pure: ``assess`` and ``choose_designations`` take a club's
players and its season's state and know nothing of the database. The second half reads and
writes the save: a club's view, the checks a move or a renewal must pass, the fee of a trade
within MLS (paid in GAM) or of a sale out of it (95% to the club, up to $3M a season of it as
GAM), the season's allocations, the AI's repairs, and the user's choices.

Money is euro cents a year here (wages are yearly: weekly * 52); MLS's dollar figures are
converted at finance.yaml's dollar rate. Nothing here is random.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from sqlalchemy import Connection, Row, bindparam, text

from footsim.defs.mls import MlsRulesDef
from footsim.transfers.valuation import years_old
from footsim.world.context import World
from footsim.world.meta import CareerMeta
from footsim.world.squads import display_name

SENIOR = "senior"
SUPPLEMENTAL = "supplemental"
DP = "dp"
U22 = "u22"
HOMEGROWN = "homegrown"
GA = "generation_adidas"
DESIGNATIONS = (SENIOR, SUPPLEMENTAL, DP, U22, HOMEGROWN, GA)
SLOTS = (SENIOR, SUPPLEMENTAL)  # the two rosters
WEEKS = 52

Money = Callable[[int], str]  # euro cents as the user reads them


class RosterRefused(Exception):
    """Why a roster choice can't be made (shown to the user)."""


def dollars(cents: int, per_euro: float) -> str:
    """Euro cents as dollars, MLS's way: $6,425,000."""
    return f"${round(cents / 100 * per_euro):,}"


# --- the rules in euros --------------------------------------------------------------------


@dataclass(frozen=True)
class Figures:
    """MLS's rules with their figures in euro cents a year."""

    rules: MlsRulesDef
    per_euro: float  # dollars a euro

    def c(self, usd: float) -> int:
        return round(usd / self.per_euro * 100)

    @property
    def budget(self) -> int:
        return self.c(self.rules.salary_budget)

    @property
    def max_charge(self) -> int:
        return self.c(self.rules.max_charge)

    @property
    def senior_minimum(self) -> int:
        return self.c(self.rules.senior_minimum)

    @property
    def reserve_minimum(self) -> int:
        return self.c(self.rules.reserve_minimum)

    @property
    def tam_ceiling(self) -> int:
        return self.c(self.rules.tam.ceiling)

    @property
    def tam_floor(self) -> int:
        return self.c(self.rules.tam.floor)

    @property
    def gam_floor(self) -> int:
        return self.c(self.rules.gam.floor)

    @property
    def homegrown_supplemental_max(self) -> int:
        return self.c(self.rules.homegrown_supplemental_max)

    def dp_charge(self, age: int, late: bool) -> int:
        r = self.rules
        charge = self.c(r.by_age(r.dp_charges, r.dp_charge, age))
        return round(charge * r.dp_secondary_window_share) if late else charge

    def u22_charge(self, age: int) -> int:
        r = self.rules
        return self.c(r.by_age(r.u22_charges, r.u22_charge, age))

    def model(self, model: int) -> tuple[int, int]:
        """(Designated Players, U22 Initiative players) a roster model allows."""
        found = self.rules.roster_models[model]
        return found.designated_players, found.u22_players


def figures(world: World) -> Figures:
    return Figures(world.defs.mls, world.defs.finance.currencies["USD"].per_euro)


# --- a club's players and its season, as the rules see them ---------------------------------


@dataclass(frozen=True)
class Member:
    """A player on an MLS club's roster."""

    player_id: int
    name: str
    wage: int  # euro cents a year the club pays him (less a borrower's share; a loan's share)
    age: int  # whole years today
    signed_age: int  # whole years when he joined the club
    international: bool  # takes an international slot
    canadian: bool
    homegrown: bool  # from this club's academy
    ga: bool  # Generation adidas this season
    late: bool = False  # joined after the secondary window opened this season
    loan: str | None = None  # "in" (here on loan) or "out" (lent out); None
    contract_wage: int | None = None  # his own contract's yearly wage (minimums); None: wage
    designation: str = SENIOR
    slot: str = SENIOR

    @property
    def full_wage(self) -> int:
        return self.contract_wage if self.contract_wage is not None else self.wage


@dataclass(frozen=True)
class ClubRules:
    """A club's season under the rules."""

    model: int  # 1 or 2
    tam: int  # this season's TAM, euro cents
    gam: int  # GAM it can spend on buy-downs
    international_slots: int
    canadian: bool


@dataclass(frozen=True)
class Charge:
    player_id: int
    base: int  # before allocation money
    tam: int
    gam: int

    @property
    def charge(self) -> int:
        return self.base - self.tam - self.gam


@dataclass(frozen=True)
class Problem:
    """A rule a roster breaks: ``text`` for the roster page, ``refusal`` for a refused move."""

    code: str
    text: str
    refusal: str
    amount: int = 0  # how far over (cents for money, players for slots)


@dataclass(frozen=True)
class Report:
    """Where a roster stands under the rules."""

    members: list[Member]
    charges: dict[int, Charge]
    used: int  # the Senior Roster's charges after buy-downs, empty slots included
    budget: int
    empty_slots: int
    tam_used: int
    gam_used: int
    senior: int
    supplemental: int
    dps: int
    u22s: int
    internationals: int
    canadians: int
    problems: list[Problem]

    @property
    def compliant(self) -> bool:
        return not self.problems

    @property
    def left(self) -> int:
        return self.budget - self.used


def supplemental_tiers(fig: Figures, m: Member) -> tuple[bool, bool]:
    """Whether he may take slots 21-24 (senior minimum, Generation adidas, Homegrown) and slots
    25-30 (reserve minimum, 24 or younger)."""
    homegrown = m.homegrown and m.full_wage <= fig.homegrown_supplemental_max
    upper = m.ga or homegrown or m.full_wage <= fig.senior_minimum
    lower = m.age <= fig.rules.reserve_max_age and (
        m.ga or homegrown or m.full_wage <= fig.reserve_minimum)
    return upper, lower


def tiers_fit(fig: Figures, players: Iterable[Member]) -> bool:
    """Whether these Supplemental players fit its slots, each in a tier he may take."""
    upper_only = lower_only = total = 0
    for m in players:
        upper, lower = supplemental_tiers(fig, m)
        if not (upper or lower):
            return False
        upper_only += int(upper and not lower)
        lower_only += int(lower and not upper)
        total += 1
    r = fig.rules
    return (upper_only <= r.supplemental_senior_slots
            and lower_only <= r.supplemental_slots - r.supplemental_senior_slots
            and total <= r.supplemental_slots)


def not_allowed(fig: Figures, m: Member, designation: str, slot: str) -> str | None:
    """Why he can't have this designation on this roster, or None."""
    r = fig.rules
    if designation not in DESIGNATIONS or slot not in SLOTS:
        return "There's no such designation."
    fixed = {DP: SENIOR, U22: SENIOR, SENIOR: SENIOR, SUPPLEMENTAL: SUPPLEMENTAL, GA: SUPPLEMENTAL}
    if designation in fixed and slot != fixed[designation]:
        return "That designation is on the other roster."
    if designation == U22:
        if m.signed_age > r.u22_signing_max_age:
            return (f"{m.name} was {m.signed_age} when he signed: a U22 Initiative player signs "
                    f"at {r.u22_signing_max_age} or younger.")
        if m.age > r.u22_max_age:
            return f"{m.name} is past the U22 Initiative's age ({r.u22_max_age})."
        if m.full_wage > fig.c(r.u22_max_wage):
            return f"{m.name} is paid too much for the U22 Initiative."
    if designation == HOMEGROWN and not m.homegrown:
        return f"{m.name} isn't a Homegrown player."
    if designation == GA and not m.ga:
        return f"{m.name} isn't a Generation adidas player."
    if slot == SUPPLEMENTAL and not any(supplemental_tiers(fig, m)):
        return (f"{m.name} can't be on the Supplemental Roster: he's paid too much, or too old "
                "for its reserve slots.")
    return None


def base_charge(fig: Figures, m: Member) -> int:
    """His charge before allocation money."""
    if m.slot == SUPPLEMENTAL:
        return 0
    if m.designation == DP:
        return min(m.wage, fig.dp_charge(m.age, m.late))
    if m.designation == U22:
        return min(m.wage, fig.u22_charge(m.age))
    return m.wage


def _buyable(m: Member) -> bool:
    """A Senior Roster player allocation money can buy down (not a DP or a U22 player)."""
    return m.slot == SENIOR and m.designation not in (DP, U22)


def buy_downs(fig: Figures, club: ClubRules, members: list[Member]
              ) -> tuple[dict[int, Charge], list[int]]:
    """Each player's charge, and TAM's and GAM's buy-downs as a club would make them: first
    what each player paid above the maximum needs to come down to it (TAM if he's paid up to its
    ceiling, then GAM), then, while the Senior Roster is over the budget, TAM down to its floor,
    then GAM, the dearest charges first. Also returns the players nothing can bring down to the
    maximum (they would have to be Designated Players)."""
    base = {m.player_id: base_charge(fig, m) for m in members}
    tam = dict.fromkeys(base, 0)
    gam = dict.fromkeys(base, 0)
    tam_left, gam_left = club.tam, club.gam

    def now(pid: int) -> int:
        return base[pid] - tam[pid] - gam[pid]

    def gam_room(pid: int) -> int:
        cap = round(fig.rules.gam.max_share * base[pid])
        return max(0, min(now(pid) - fig.gam_floor, cap - gam[pid]))

    def tam_eligible(m: Member) -> bool:
        return fig.max_charge < m.wage <= fig.tam_ceiling

    buyable = [m for m in members if _buyable(m)]
    unbought = []
    for m in sorted(buyable, key=lambda m: (-base[m.player_id], m.player_id)):
        pid = m.player_id
        need = now(pid) - fig.max_charge
        if need <= 0:
            continue
        if tam_eligible(m):
            t = min(need, tam_left)
            tam[pid] += t
            tam_left -= t
            need -= t
        if need > 0:
            g = min(need, gam_room(pid), gam_left)
            gam[pid] += g
            gam_left -= g
            need -= g
        if need > 0:
            unbought.append(pid)
    seniors = [m for m in members if m.slot == SENIOR]
    empty = max(0, fig.rules.empty_slot_below - len(seniors))
    over = sum(now(m.player_id) for m in seniors) + empty * fig.senior_minimum - fig.budget
    for m in sorted((m for m in buyable if tam_eligible(m)),
                    key=lambda m: (-now(m.player_id), m.player_id)):
        if over <= 0 or tam_left <= 0:
            break
        t = max(0, min(now(m.player_id) - fig.tam_floor, tam_left, over))
        tam[m.player_id] += t
        tam_left -= t
        over -= t
    for m in sorted(buyable, key=lambda m: (-now(m.player_id), m.player_id)):
        if over <= 0 or gam_left <= 0:
            break
        g = min(gam_room(m.player_id), gam_left, over)
        gam[m.player_id] += g
        gam_left -= g
        over -= g
    return {pid: Charge(pid, base[pid], tam[pid], gam[pid]) for pid in base}, unbought


def assess(fig: Figures, club: ClubRules, members: list[Member],
           money: Money | None = None, headroom: int = 0) -> Report:
    """Where ``members`` (with their designations) stand under the rules. ``headroom``: a
    planner's margin, kept off the budget."""
    r = fig.rules
    money = money or (lambda cents: dollars(cents, fig.per_euro))
    charges, unbought = buy_downs(fig, replace(club), members)
    seniors = [m for m in members if m.slot == SENIOR]
    supplemental = [m for m in members if m.slot == SUPPLEMENTAL]
    empty = max(0, r.empty_slot_below - len(seniors))
    used = sum(charges[m.player_id].charge for m in seniors) + empty * fig.senior_minimum
    budget = fig.budget - headroom
    dps = sum(1 for m in members if m.designation == DP)
    u22s = sum(1 for m in members if m.designation == U22)
    internationals = sum(1 for m in members if m.international)
    canadians = sum(1 for m in members if m.canadian)
    dp_slots, u22_slots = fig.model(club.model)
    problems: list[Problem] = []
    for m in members:
        reason = not_allowed(fig, m, m.designation, m.slot)
        if reason is not None:
            problems.append(Problem("designation", reason, reason))
    if internationals > club.international_slots:
        problems.append(Problem(
            "international",
            f"{internationals} internationals for {club.international_slots} international "
            "slots.", "No international slot free", internationals - club.international_slots))
    if dps > dp_slots:
        problems.append(Problem(
            "dp", f"{dps} Designated Players: Model {club.model} allows {dp_slots}.",
            f"All {dp_slots} Designated Player slots are full", dps - dp_slots))
    if u22s > u22_slots:
        problems.append(Problem(
            "u22", f"{u22s} U22 Initiative players: Model {club.model} allows {u22_slots}.",
            f"All {u22_slots} U22 Initiative slots are full", u22s - u22_slots))
    if len(seniors) > r.senior_slots:
        problems.append(Problem(
            "senior", f"{len(seniors)} players on the Senior Roster: it has {r.senior_slots} "
            "slots.", f"The Senior Roster is full ({r.senior_slots} slots)",
            len(seniors) - r.senior_slots))
    if len(supplemental) > r.supplemental_slots:
        problems.append(Problem(
            "supplemental", f"{len(supplemental)} players on the Supplemental Roster: it has "
            f"{r.supplemental_slots} slots.",
            f"The Supplemental Roster is full ({r.supplemental_slots} slots)",
            len(supplemental) - r.supplemental_slots))
    elif not tiers_fit(fig, supplemental):
        problems.append(Problem(
            "tiers", f"The Supplemental Roster's players don't fit its tiers: slots 21-"
            f"{20 + r.supplemental_senior_slots} take senior-minimum, Generation adidas and "
            f"Homegrown players; the others, players {r.reserve_max_age} or younger on the "
            "reserve minimum.", "No Supplemental Roster slot he can take"))
    for pid in unbought:
        name = next(m.name for m in members if m.player_id == pid)
        problems.append(Problem(
            "unbought", f"{name} is paid more than allocation money can buy down to the maximum "
            f"charge ({money(fig.max_charge)}): he has to be a Designated Player.",
            f"{name} would have to be a Designated Player: allocation money can't buy his "
            "charge down to the maximum"))
    if used > budget:
        problems.append(Problem(
            "budget", f"Over the salary budget by {money(used - budget)} after allocation "
            "money.", f"Over the salary budget by {money(used - budget)} after allocation money",
            used - budget))
    for m in members:
        if m.loan == "in":
            continue
        least = fig.senior_minimum if m.slot == SENIOR else fig.reserve_minimum
        if m.full_wage < least:
            problems.append(Problem(
                "minimum", f"{m.name} is paid below MLS's minimum for his roster "
                f"({money(least)}).", f"His wage is below MLS's minimum ({money(least)})",
                least - m.full_wage))
    if club.canadian and canadians < r.canadian_minimum:
        problems.append(Problem(
            "canadian", f"A Canadian club keeps at least {r.canadian_minimum} Canadians on its "
            f"roster: {canadians} now.",
            f"A Canadian club keeps at least {r.canadian_minimum} Canadians",
            r.canadian_minimum - canadians))
    gam_used = sum(c.gam for c in charges.values())
    tam_used = sum(c.tam for c in charges.values())
    return Report(members, charges, used, budget, empty, tam_used, gam_used, len(seniors),
                  len(supplemental), dps, u22s, internationals, canadians, problems)


def new_problems(before: Report, after: Report) -> list[Problem]:
    """The problems ``after`` has that ``before`` hadn't, or has worse."""
    old = {(p.code, p.text): p.amount for p in before.problems}
    old_codes = {p.code: p.amount for p in before.problems if p.code not in ("designation",)}
    result = []
    for p in after.problems:
        if (p.code, p.text) in old:
            continue
        if p.code in old_codes and p.amount <= old_codes[p.code]:
            continue
        result.append(p)
    return result


def default_place(m: Member) -> Member:
    """Where a player goes before anything is chosen: Generation adidas on the Supplemental
    Roster, a Homegrown player as Homegrown, everyone else senior."""
    if m.ga:
        return replace(m, designation=GA, slot=SUPPLEMENTAL)
    if m.homegrown:
        return replace(m, designation=HOMEGROWN, slot=SENIOR)
    return replace(m, designation=SENIOR, slot=SENIOR)


def choose_designations(fig: Figures, club: ClubRules, members: list[Member]) -> list[Member]:
    """The designations a club would choose, from scratch: its Designated Player and U22
    Initiative slots for the players they save the most charge on, then the Supplemental Roster
    for the players eligible, the best paid first, while it saves charge (or the Senior Roster
    is over its slots)."""
    r = fig.rules
    placed = {m.player_id: default_place(m) for m in members}
    dp_slots, u22_slots = fig.model(club.model)
    options: list[tuple[int, int, int, str]] = []  # (-saving, U22 first, id, designation)
    for m in members:
        if m.ga:
            continue
        dp_saving = m.wage - fig.dp_charge(m.age, m.late)
        if dp_saving > 0:
            options.append((-dp_saving, 1, m.player_id, DP))
        if not_allowed(fig, m, U22, SENIOR) is None:
            u22_saving = m.wage - fig.u22_charge(m.age)
            if u22_saving > 0:
                options.append((-u22_saving, 0, m.player_id, U22))
    options.sort()
    taken = {DP: 0, U22: 0}
    limits = {DP: dp_slots, U22: u22_slots}
    chosen: set[int] = set()
    for _, _, pid, designation in options:
        if pid in chosen or taken[designation] >= limits[designation]:
            continue
        # A DP slot is worth it only for a player paid above what TAM can reach, or the
        # biggest savings; the order already ranks savings.
        placed[pid] = replace(placed[pid], designation=designation, slot=SENIOR)
        taken[designation] += 1
        chosen.add(pid)
    supplemental = [m for m in placed.values() if m.slot == SUPPLEMENTAL]
    seniors = len(placed) - len(supplemental)
    candidates = sorted((m for m in placed.values()
                         if m.slot == SENIOR and m.player_id not in chosen
                         and any(supplemental_tiers(fig, m))),
                        key=lambda m: (-m.wage, m.player_id))
    for m in candidates:
        if len(supplemental) >= r.supplemental_slots:
            break
        moved = replace(m, designation=HOMEGROWN if m.homegrown else SUPPLEMENTAL,
                        slot=SUPPLEMENTAL)
        if not tiers_fit(fig, [*supplemental, moved]):
            continue
        cost = fig.senior_minimum if seniors - 1 < r.empty_slot_below else 0
        if seniors > r.senior_slots or m.wage > cost:
            supplemental.append(moved)
            placed[m.player_id] = moved
            seniors -= 1
    return [placed[m.player_id] for m in members]


def placements(fig: Figures, m: Member) -> list[Member]:
    """The designations a newcomer could take, as a club tries them: the Supplemental Roster
    first (it costs nothing), then senior, then U22, then a DP slot."""
    tries = [(GA, SUPPLEMENTAL), (HOMEGROWN, SUPPLEMENTAL), (SUPPLEMENTAL, SUPPLEMENTAL),
             (HOMEGROWN, SENIOR), (SENIOR, SENIOR), (U22, SENIOR), (DP, SENIOR)]
    result = [replace(m, designation=d, slot=s) for d, s in tries
              if not_allowed(fig, m, d, s) is None]
    if m.homegrown:
        result = [p for p in result if p.designation != SENIOR]
    return result


def natural_place(fig: Figures, m: Member) -> Member:
    """Where a newcomer would go if nothing fits: a DP slot if he's paid above TAM's reach, a
    U22 slot if he's young and paid above the maximum, else as default."""
    if m.wage > fig.tam_ceiling:
        return replace(m, designation=DP, slot=SENIOR)
    if m.wage > fig.max_charge and not_allowed(fig, m, U22, SENIOR) is None:
        return replace(m, designation=U22, slot=SENIOR)
    return default_place(m)


def place_newcomer(fig: Figures, club: ClubRules, members: list[Member], newcomer: Member,
                   money: Money | None = None) -> tuple[Member, Report]:
    """A newcomer at a club that keeps its other players' designations (the user's): the
    first designation that leaves the club compliant, or, if none does, the natural one."""
    for option in placements(fig, newcomer):
        report = assess(fig, club, [*members, option], money)
        if report.compliant:
            return option, report
    option = natural_place(fig, newcomer)
    return option, assess(fig, club, [*members, option], money)


# --- the save ------------------------------------------------------------------------------


def _season_year(conn: Connection, season_id: int) -> int:
    start = conn.execute(text("SELECT start_date FROM season WHERE id = :s"),
                         {"s": season_id}).scalar()
    return date.fromisoformat(start).year if start else 2026


def mls_club_ids(conn: Connection, world: World, season_id: int) -> set[int]:
    """The clubs MLS's rules apply to this season: its league's members, or, before the league is
    played in the save, the clubs the source data has in MLS."""
    rules = world.defs.mls
    ids = {int(r.club_id) for r in conn.execute(text(
        "SELECT m.club_id FROM club_league_membership m JOIN competition c "
        "ON c.id = m.competition_id WHERE c.key = :k AND m.season_id = :s"),
        {"k": rules.league, "s": season_id})}
    if ids:
        return ids
    return {int(r.id) for r in conn.execute(text("SELECT id FROM club WHERE source_league = :l"),
                                            {"l": rules.source_league})}


def state(conn: Connection, club_id: int, season_id: int) -> Row[Any] | None:
    """A club's season under the rules (an ``mls_club_season`` row), if it has one."""
    return conn.execute(text("SELECT * FROM mls_club_season WHERE club_id = :c AND "
                             "season_id = :s"), {"c": club_id, "s": season_id}).first()


def under_rules(conn: Connection, club_id: int | None, season_id: int) -> bool:
    """Whether a club plays by the rules now (it's an MLS club whose season has begun under
    them)."""
    return club_id is not None and state(conn, club_id, season_id) is not None


def _club_country(conn: Connection, world: World, club_id: int) -> str:
    rules = world.defs.mls
    row = conn.execute(text("SELECT c.name, n.code FROM club c LEFT JOIN nation n "
                            "ON n.id = c.nation_id WHERE c.id = :c"), {"c": club_id}).one()
    if row.name in rules.canadian_clubs:
        return "CAN"
    return str(row.code) if row.code in rules.domestic_nations else "USA"


def club_rules(conn: Connection, world: World, club_id: int, season_id: int,
               gam_spent: int = 0, reserve: bool = False) -> ClubRules:
    """A club's season as the rules need it. ``gam_spent``: GAM it's about to pay out;
    ``reserve``: the AI keeps a share of its GAM out of buy-downs."""
    row = state(conn, club_id, season_id)
    assert row is not None
    gam = max(0, int(row.gam_cents) + int(row.gam_expiring_cents) - gam_spent)
    if reserve:
        gam = round(gam * (1 - world.defs.mls.ai.gam_reserve_share))
    return ClubRules(model=int(row.roster_model), tam=int(row.tam_cents), gam=gam,
                     international_slots=int(row.international_slots),
                     canadian=_club_country(conn, world, club_id) == "CAN")


def _secondary_window_start(conn: Connection, world: World, club_id: int,
                            season_id: int) -> date | None:
    from footsim.world.windows import _base_calendar, _season_calendar, club_window_nation

    calendar = _season_calendar(_base_calendar(world, club_window_nation(conn, club_id,
                                                                         season_id)), season_id)
    windows = sorted(calendar.transfer_windows, key=lambda w: w.start)
    return windows[1].start if len(windows) > 1 else None


def load_members(conn: Connection, world: World, meta: CareerMeta, club_id: int,
                 day: date) -> tuple[list[Member], dict[int, tuple[str, str]]]:
    """A club's roster: its players of contract age, those it has lent out included (they keep
    their slots) and those it has borrowed. Returns the players with their designations as
    stored (``default_place`` for one with none) and the stored ones by player."""
    rules = world.defs.mls
    fig = figures(world)
    adult = world.defs.lifecycle.youth.contract_age
    country = _club_country(conn, world, club_id)
    domestic = set(rules.domestic_nations.get(country, []))
    second = _secondary_window_start(conn, world, club_id, meta.season_id)
    season_start = conn.execute(text("SELECT start_date FROM season WHERE id = :s"),
                                {"s": meta.season_id}).scalar()
    rows = conn.execute(text(
        "SELECT k.person_id AS id, k.kind, k.start_date, k.wage_weekly_cents AS wage, "
        "p.birth_date, p.first_name, p.last_name, p.known_as, n.code AS nation, "
        "(SELECT l.wage_weekly_cents FROM contract l WHERE l.person_id = k.person_id "
        " AND l.is_active = 1 AND l.kind = 'loan') AS lent, "
        "(SELECT o.wage_weekly_cents FROM contract o WHERE o.person_id = k.person_id "
        " AND o.is_active = 1 AND o.kind != 'loan') AS own_wage, "
        "(SELECT 1 FROM contract y WHERE y.person_id = k.person_id AND y.club_id = k.club_id "
        " AND y.kind = 'youth' LIMIT 1) AS academy, "
        "s.homegrown_club_id, COALESCE(s.green_card, 0) AS green_card, s.ga_until_season "
        "FROM contract k JOIN person p ON p.id = k.person_id "
        "LEFT JOIN nation n ON n.id = p.nation_id LEFT JOIN mls_player s ON s.player_id = "
        "k.person_id WHERE k.club_id = :c AND k.is_active = 1 "
        "AND k.kind IN ('player', 'youth', 'loan') ORDER BY k.person_id"),
        {"c": club_id}).all()
    stored = {int(r.player_id): (str(r.designation), str(r.slot)) for r in conn.execute(text(
        "SELECT player_id, designation, slot FROM mls_roster WHERE season_id = :s AND "
        "club_id = :c"), {"s": meta.season_id, "c": club_id})}
    members = []
    for r in rows:
        if r.kind == "youth" and years_old(r.birth_date, day) < adult:
            continue
        weekly = int(r.wage)
        loan = None
        contract_wage = None
        if r.kind == "loan":
            loan = "in"
            contract_wage = int(r.own_wage or r.wage) * WEEKS
        elif r.lent is not None:
            loan = "out"
            contract_wage = weekly * WEEKS
            weekly = max(0, weekly - int(r.lent))
        homegrown = bool(r.academy) or r.homegrown_club_id == club_id
        joined = date.fromisoformat(r.start_date)
        late = (second is not None and season_start is not None and joined >= second
                and joined.isoformat() >= season_start)
        name = display_name(r.first_name, r.last_name, r.known_as)
        m = Member(
            player_id=int(r.id), name=name, wage=weekly * WEEKS,
            age=int(years_old(r.birth_date, day)),
            signed_age=int(years_old(r.birth_date, min(joined, day))),
            international=not (r.nation in domestic or homegrown or r.green_card),
            canadian=r.nation == "CAN", homegrown=homegrown,
            ga=r.ga_until_season is not None and int(r.ga_until_season) >= meta.season_id,
            late=late, loan=loan, contract_wage=contract_wage)
        found = stored.get(m.player_id)
        if found is not None and not_allowed(fig, m, *found) is None:
            m = replace(m, designation=found[0], slot=found[1])
        else:
            m = default_place(m)
        members.append(m)
    return members, stored


def _is_ai(meta: CareerMeta, club_id: int) -> bool:
    return club_id != meta.user_club_id


def club_report(conn: Connection, world: World, meta: CareerMeta, club_id: int, day: date,
                money: Money | None = None) -> Report:
    """Where a club stands now. An AI club's designations are its own choice (made afresh);
    the user's are theirs, a player without one placed as a club would place him."""
    fig = figures(world)
    club = club_rules(conn, world, club_id, meta.season_id)
    members, stored = load_members(conn, world, meta, club_id, day)
    if _is_ai(meta, club_id):
        return assess(fig, club, choose_designations(fig, club, members), money)
    kept = [m for m in members if m.player_id in stored
            and (m.designation, m.slot) == stored[m.player_id]]
    for m in members:
        if m.player_id in {k.player_id for k in kept}:
            continue
        placed, _ = place_newcomer(fig, club, kept, m, money)
        kept.append(placed)
    order = {m.player_id: n for n, m in enumerate(members)}
    kept.sort(key=lambda m: order[m.player_id])
    return assess(fig, club, kept, money)


def save_report(conn: Connection, meta: CareerMeta, club_id: int, report: Report) -> None:
    """Store a club's designations and the GAM its buy-downs take."""
    conn.execute(text("DELETE FROM mls_roster WHERE season_id = :s AND club_id = :c"),
                 {"s": meta.season_id, "c": club_id})
    if report.members:
        conn.execute(text(
            "INSERT OR REPLACE INTO mls_roster (season_id, player_id, club_id, designation, "
            "slot) VALUES (:s, :p, :c, :d, :slot)"),
            [{"s": meta.season_id, "p": m.player_id, "c": club_id, "d": m.designation,
              "slot": m.slot} for m in report.members])
        conn.execute(text(
            "INSERT OR IGNORE INTO mls_player (player_id, green_card, since_season) "
            "VALUES (:p, 0, :s)"), [{"p": m.player_id, "s": meta.season_id}
                                    for m in report.members if m.loan != "in"])
    conn.execute(text("UPDATE mls_club_season SET gam_committed_cents = :g WHERE club_id = :c "
                      "AND season_id = :s"),
                 {"g": report.gam_used, "c": club_id, "s": meta.season_id})


def money_for(world: World, meta: CareerMeta) -> Money:
    from footsim.world.money import money_text

    return lambda cents: money_text(cents / 100, world, meta.currency)


def sync_clubs(conn: Connection, world: World, meta: CareerMeta, clubs: Iterable[int | None],
               day: date) -> None:
    """After a change at these clubs: their designations again, the GAM their buy-downs take,
    and the league's fee for a third Designated Player."""
    synced = False
    for club_id in sorted({c for c in clubs if c is not None}):
        if not under_rules(conn, club_id, meta.season_id):
            continue
        if _is_ai(meta, club_id):  # its new designations may put a player on a dearer roster
            raise_to_minimum(conn, world, meta, club_id, day)
        save_report(conn, meta, club_id, club_report(conn, world, meta, club_id, day))
        synced = True
    if synced:
        charge_dp_fees(conn, world, meta, day)


def _gam(conn: Connection, meta: CareerMeta, club_id: int, kind: str, amount: int, day: date,
         ref: int | None = None) -> None:
    """Move a club's GAM (``amount`` may be negative: spent from its expiring GAM first)."""
    if not amount:
        return
    row = state(conn, club_id, meta.season_id)
    assert row is not None
    main, expiring = int(row.gam_cents), int(row.gam_expiring_cents)
    if amount < 0:
        from_expiring = min(expiring, -amount)
        expiring -= from_expiring
        main += amount + from_expiring
    else:
        main += amount
    conn.execute(text("UPDATE mls_club_season SET gam_cents = :g, gam_expiring_cents = :e "
                      "WHERE club_id = :c AND season_id = :s"),
                 {"g": main, "e": expiring, "c": club_id, "s": meta.season_id})
    conn.execute(text("INSERT INTO mls_gam (club_id, season_id, date, kind, amount_cents, "
                      "ref_id) VALUES (:c, :s, :d, :k, :a, :r)"),
                 {"c": club_id, "s": meta.season_id, "d": day.isoformat(), "k": kind,
                  "a": amount, "r": ref})


def gam_held(conn: Connection, club_id: int, season_id: int) -> int:
    row = state(conn, club_id, season_id)
    if row is None:
        return 0
    return int(row.gam_cents) + int(row.gam_expiring_cents)


# --- the league's fee for a third Designated Player ------------------------------------------


def charge_dp_fees(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[int]:
    """The league's fee from each club with a third Designated Player this season, once (none
    when one of its DPs is a young DP). Returns the clubs charged."""
    from footsim.world.finance import Entry, post

    rules = world.defs.mls
    fig = figures(world)
    due = []
    for r in conn.execute(text(
            "SELECT s.club_id, (SELECT COUNT(*) FROM mls_roster m WHERE m.season_id = s.season_id "
            " AND m.club_id = s.club_id AND m.designation = 'dp') AS dps, "
            "(SELECT MAX(p.birth_date) FROM mls_roster m JOIN person p ON p.id = m.player_id "
            " WHERE m.season_id = s.season_id AND m.club_id = s.club_id "
            " AND m.designation = 'dp') AS youngest "
            "FROM mls_club_season s JOIN club_finance f ON f.club_id = s.club_id "
            "WHERE s.season_id = :s AND s.dp_fee_paid = 0 ORDER BY s.club_id"),
            {"s": meta.season_id}):
        if int(r.dps) < 3:
            continue
        if int(years_old(r.youngest, day)) <= rules.young_dp_max_age:
            continue
        due.append(int(r.club_id))
    if not due:
        return []
    post(conn, day, meta.season_id, [Entry(c, "adjustment", -fig.c(rules.third_dp_fee))
                                     for c in due])
    conn.execute(text("UPDATE mls_club_season SET dp_fee_paid = 1 WHERE club_id = :c AND "
                      "season_id = :s"), [{"c": c, "s": meta.season_id} for c in due])
    return due


# --- AI clubs keep to the rules ----------------------------------------------------------------


def _release(conn: Connection, meta: CareerMeta, club_id: int, player_id: int,
             day: date) -> None:
    """An MLS club lets a player go to fix its roster (free agency, as any release). At the
    career's start (before any club has finances) it's part of building the world, as
    ``lifecycle.trim_squads`` is: the history has no row for it."""
    from footsim.world.transfers import _drop_from_lineup, void_offers

    conn.execute(text("UPDATE contract SET is_active = 0, end_date = :d, listed = 0 WHERE "
                      "person_id = :p AND club_id = :c AND is_active = 1 AND kind != 'loan'"),
                 {"d": day.isoformat(), "p": player_id, "c": club_id})
    started = conn.execute(text("SELECT 1 FROM club_finance LIMIT 1")).first() is not None
    if started:
        conn.execute(text(
            "INSERT INTO transfer (player_id, from_club_id, to_club_id, date, season_id, kind, "
            "fee_cents, wage_weekly_cents, contract_end, by_user) VALUES (:p, :c, NULL, :d, :s, "
            "'release', 0, 0, NULL, :u)"),
            {"p": player_id, "c": club_id, "d": day.isoformat(), "s": meta.season_id,
             "u": int(club_id == meta.user_club_id)})
    conn.execute(text("DELETE FROM mls_roster WHERE season_id = :s AND player_id = :p"),
                 {"s": meta.season_id, "p": player_id})
    _drop_from_lineup(conn, club_id, player_id)
    void_offers(conn, player_id)


def _keepers(conn: Connection, ids: list[int]) -> set[int]:
    from footsim.world.overall_history import primary_positions

    return {p for p, pos in primary_positions(conn, ids).items() if pos == "GK"}


def _release_order(conn: Connection, world: World, members: list[Member], report: Report,
                   problem: Problem) -> list[int]:
    """Whom a club would let go first for ``problem``: for money, the dearest charges outside its
    best eleven; for slots, its weakest (a young player counts some of the potential he has yet
    to reach); for international slots, its weakest international."""
    from footsim.world.overall_history import player_overalls

    rules = world.defs.lifecycle.squads
    ids = [m.player_id for m in members]
    overall = player_overalls(conn, world, ids)
    potential = {int(r.person_id): int(r.pa_hidden) for r in conn.execute(
        text("SELECT person_id, pa_hidden FROM player WHERE person_id IN :ids")
        .bindparams(bindparam("ids", expanding=True)), {"ids": ids})}
    by_id = {m.player_id: m for m in members}

    def score(pid: int) -> float:
        m = by_id[pid]
        room = max(0, potential.get(pid, 0) - overall.get(pid, 0)) if m.age <= rules.young_until \
            else 0
        return overall.get(pid, 0) + rules.potential_weight * room

    free = [m.player_id for m in members if m.loan is None and m.designation != DP]
    if problem.code in ("budget", "unbought"):
        best = set(sorted(ids, key=lambda p: (-overall.get(p, 0), p))[:11])
        dear = [p for p in free if p not in best and report.charges[p].charge > 0]
        return sorted(dear, key=lambda p: (-report.charges[p].charge, p)) + sorted(
            (p for p in free if p not in dear), key=lambda p: (score(p), p))
    if problem.code == "international":
        return sorted((p for p in free if by_id[p].international), key=lambda p: (score(p), p))
    if problem.code in ("senior", "supplemental", "tiers"):
        roster = SENIOR if problem.code == "senior" else SUPPLEMENTAL
        return sorted((p for p in free if by_id[p].slot == roster), key=lambda p: (score(p), p))
    return sorted(free, key=lambda p: (score(p), p))


def _buy_slot(conn: Connection, world: World, meta: CareerMeta, buyer: int, day: date,
              sellers: Iterable[int]) -> bool:
    """An AI club short of international slots buys one for GAM from the MLS club with the most
    to spare (the user's club sells only by the user's choice)."""
    rules = world.defs.mls
    price = figures(world).c(rules.slot_price_gam)
    if gam_held(conn, buyer, meta.season_id) < price:
        return False
    spare = []
    for club_id in sorted(sellers):
        if club_id in (buyer, meta.user_club_id):
            continue
        row = state(conn, club_id, meta.season_id)
        if row is None:
            continue
        members, _ = load_members(conn, world, meta, club_id, day)
        free = int(row.international_slots) - sum(1 for m in members if m.international)
        if free > rules.ai.spare_slots_kept:
            spare.append((-free, club_id))
    if not spare:
        return False
    seller = sorted(spare)[0][1]
    trade_slot(conn, meta, seller, buyer, price, day)
    return True


def trade_slot(conn: Connection, meta: CareerMeta, seller: int, buyer: int, price: int,
               day: date) -> None:
    """An international slot changes clubs for the season, for ``price`` of GAM."""
    conn.execute(text("UPDATE mls_club_season SET international_slots = international_slots + "
                      ":n WHERE club_id = :c AND season_id = :s"),
                 [{"n": -1, "c": seller, "s": meta.season_id},
                  {"n": 1, "c": buyer, "s": meta.season_id}])
    _gam(conn, meta, buyer, "slot", -price, day, seller)
    _gam(conn, meta, seller, "slot", price, day, buyer)


def raise_to_minimum(conn: Connection, world: World, meta: CareerMeta, club_id: int,
                     day: date) -> None:
    """MLS's minimums: a player paid below his roster's minimum gets it (a youngster joining
    the roster from the academy, say)."""
    fig = figures(world)
    report = club_report(conn, world, meta, club_id, day)
    raises = []
    for m in report.members:
        if m.loan == "in":
            continue
        least = fig.senior_minimum if m.slot == SENIOR else fig.reserve_minimum
        if m.full_wage < least:
            raises.append({"p": m.player_id, "c": club_id, "w": _weekly(least)})
    if raises:
        conn.execute(text("UPDATE contract SET wage_weekly_cents = :w WHERE person_id = :p AND "
                          "club_id = :c AND is_active = 1 AND kind != 'loan'"), raises)


def _weekly(yearly_cents: int) -> int:
    """A yearly wage as the weekly one a contract keeps (whole euros), never below it."""
    return -(-yearly_cents // (WEEKS * 100)) * 100


def fix_club(conn: Connection, world: World, meta: CareerMeta, club_id: int, day: date,
             all_clubs: Iterable[int] = ()) -> list[str]:
    """An AI club makes its roster compliant: its designations afresh, its minimum wages, an
    international slot bought where one is to be had, then releases, whom it would miss least
    first. Returns what it couldn't fix."""
    floors = world.defs.lifecycle.squads
    raise_to_minimum(conn, world, meta, club_id, day)
    for _ in range(40):
        report = club_report(conn, world, meta, club_id, day)
        if report.compliant:
            save_report(conn, meta, club_id, report)
            return []
        problem = report.problems[0]
        if problem.code == "international" and _buy_slot(conn, world, meta, club_id, day,
                                                         all_clubs):
            continue
        if problem.code == "minimum":
            raise_to_minimum(conn, world, meta, club_id, day)
            continue
        if problem.code in ("canadian", "designation"):
            save_report(conn, meta, club_id, report)
            return [problem.text]
        members = report.members
        keepers = _keepers(conn, [m.player_id for m in members])
        released = False
        for pid in _release_order(conn, world, members, report, problem):
            if len(members) - 1 < floors.user_min_players:
                break
            if pid in keepers and len(keepers) - 1 < floors.user_min_keepers:
                continue
            _release(conn, meta, club_id, pid, day)
            released = True
            break
        if not released:
            save_report(conn, meta, club_id, report)
            return [problem.text]
    report = club_report(conn, world, meta, club_id, day)
    save_report(conn, meta, club_id, report)
    return [p.text for p in report.problems]


# --- seasons ---------------------------------------------------------------------------------


def _new_state(conn: Connection, world: World, meta: CareerMeta, club_id: int, model: int,
               gam: int, day: date) -> None:
    """A club's season row: this season's TAM, its slots, and its GAM (``gam``: what it carries
    in, before this season's allocation)."""
    rules = world.defs.mls
    fig = figures(world)
    extra = fig.c(rules.roster_models[model].extra_gam)
    conn.execute(text(
        "INSERT INTO mls_club_season (club_id, season_id, roster_model, gam_cents, "
        "gam_expiring_cents, gam_committed_cents, tam_cents, international_slots, "
        "gam_from_sales_cents, dp_fee_paid) VALUES (:c, :s, :m, :g, 0, 0, :t, :i, 0, 0)"),
        {"c": club_id, "s": meta.season_id, "m": model, "g": gam,
         "t": fig.c(rules.tam.for_year(_season_year(conn, meta.season_id))),
         "i": rules.international_slots})
    conn.execute(text("INSERT INTO mls_gam (club_id, season_id, date, kind, amount_cents) "
                      "VALUES (:c, :s, :d, 'allocation', :a)"),
                 {"c": club_id, "s": meta.season_id, "d": day.isoformat(),
                  "a": fig.c(rules.gam.annual)})
    conn.execute(text("UPDATE mls_club_season SET gam_cents = gam_cents + :a WHERE club_id = :c "
                      "AND season_id = :s"),
                 {"a": fig.c(rules.gam.annual), "c": club_id, "s": meta.season_id})
    if extra:
        conn.execute(text("UPDATE mls_club_season SET gam_expiring_cents = :e WHERE club_id = :c "
                          "AND season_id = :s"), {"e": extra, "c": club_id, "s": meta.season_id})
        conn.execute(text("INSERT INTO mls_gam (club_id, season_id, date, kind, amount_cents) "
                          "VALUES (:c, :s, :d, 'model', :a)"),
                     {"c": club_id, "s": meta.season_id, "d": day.isoformat(), "a": extra})


def _start_club(conn: Connection, world: World, meta: CareerMeta, club_id: int,
                day: date) -> None:
    """A club's first season under the rules (the career's start, or the first season the
    save has MLS): its roster trimmed to its slots, its roster model, green cards for the
    internationals beyond its slots (the oldest first: the longest in the country), Homegrown
    status for its young domestic players, Designated Player wages for its stars, the minimum
    for its depth, and the other wages cut evenly where they don't fit."""
    from footsim.world.overall_history import player_overalls

    rules = world.defs.mls
    fig = figures(world)
    start = rules.start
    members, _ = load_members(conn, world, meta, club_id, day)
    overall = player_overalls(conn, world, [m.player_id for m in members])
    total = rules.senior_slots + rules.supplemental_slots
    if len(members) > total:
        nobody = ClubRules(1, 0, 0, rules.international_slots, False)
        report = assess(fig, nobody, members)
        cut = Problem("senior", "", "", len(members) - total)
        keepers = _keepers(conn, [m.player_id for m in members])
        going: list[int] = []
        for pid in _release_order(conn, world, members, report, cut):
            if len(members) - len(going) <= total:
                break
            kept_keepers = keepers - set(going)
            if pid in keepers and len(kept_keepers) - 1 < world.defs.lifecycle.squads.keepers_kept:
                continue
            going.append(pid)
        for pid in going:
            _release(conn, meta, club_id, pid, day)
        members = [m for m in members if m.player_id not in going]
    ranked = sorted(members, key=lambda m: (-overall.get(m.player_id, 0), m.player_id))
    third = overall.get(ranked[2].player_id, 0) if len(ranked) >= 3 else 0
    model = 1 if third >= start.model1_min_third_overall else 2
    _new_state(conn, world, meta, club_id, model, 0, day)
    owned = [m for m in members if m.loan != "in"]
    status = []
    for m in owned:
        homegrown = not m.international and m.age <= start.homegrown_max_age
        status.append({"p": m.player_id, "h": club_id if homegrown else None, "g": 0,
                       "s": meta.season_id})
    over = sum(1 for m in members if m.international) - rules.international_slots
    internationals = sorted((m for m in owned if m.international),
                            key=lambda m: (-m.age, m.player_id))
    green = {m.player_id for m in internationals[:max(0, over)]}
    for row in status:
        row["g"] = int(row["p"] in green)
    if status:
        conn.execute(text(
            "INSERT INTO mls_player (player_id, homegrown_club_id, green_card, since_season) "
            "VALUES (:p, :h, :g, :s) ON CONFLICT(player_id) DO UPDATE SET "
            "homegrown_club_id = COALESCE(mls_player.homegrown_club_id, "
            "excluded.homegrown_club_id), "
            "green_card = MAX(mls_player.green_card, excluded.green_card)"), status)
    _start_wages(conn, world, meta, club_id, day, overall, model)


def _start_wages(conn: Connection, world: World, meta: CareerMeta, club_id: int, day: date,
                 overall: dict[int, int], model: int) -> None:
    rules = world.defs.mls
    fig = figures(world)
    start = rules.start
    members, _ = load_members(conn, world, meta, club_id, day)
    owned = [m for m in members if m.loan is None]
    dp_slots, _ = fig.model(model)
    ranked = sorted(owned, key=lambda m: (-overall.get(m.player_id, 0), m.player_id))
    stars = {m.player_id for m in ranked[:dp_slots]}
    # The depth beyond the Senior Roster's slots goes on the minimum, so it fits the
    # Supplemental Roster's tiers: the weakest young players in its reserve slots, then the
    # weakest others in its senior-minimum slots.
    needed = max(0, len(members) - rules.senior_slots)
    pool = sorted(ranked[11:], key=lambda m: (overall.get(m.player_id, 0), m.player_id))
    young = [m for m in pool if m.age <= rules.reserve_max_age and m.player_id not in stars]
    lower = rules.supplemental_slots - rules.supplemental_senior_slots
    depth = {m.player_id for m in young[:min(lower, needed)]}
    others = [m for m in pool if m.player_id not in depth and m.player_id not in stars]
    depth |= {m.player_id for m in others[:max(0, min(rules.supplemental_senior_slots,
                                                      needed - len(depth)))]}
    wages = {}
    for m in owned:
        wage = m.full_wage
        if m.player_id in stars:
            wage = max(wage, fig.c(start.dp_wage(overall.get(m.player_id, 0))))
        elif m.player_id in depth:
            wage = fig.reserve_minimum if m.age <= rules.reserve_max_age else fig.senior_minimum
        wages[m.player_id] = max(wage, fig.reserve_minimum)
    club = club_rules(conn, world, club_id, meta.season_id, reserve=True)
    headroom = fig.c(start.budget_headroom)

    def plan(factor: float) -> tuple[list[Member], Report]:
        trial = []
        for m in members:
            if m.loan is not None:
                trial.append(m)
                continue
            wage = wages[m.player_id]
            if m.player_id not in stars and m.player_id not in depth and wage > fig.senior_minimum:
                wage = max(fig.senior_minimum, round(wage * factor))
            trial.append(replace(m, wage=wage, contract_wage=None))
        chosen = choose_designations(fig, club, trial)
        chosen = [replace(m, wage=max(m.wage, fig.senior_minimum))
                  if m.slot == SENIOR and m.loan is None else m for m in chosen]
        return chosen, assess(fig, club, chosen, headroom=headroom)

    def fits(report: Report) -> bool:
        return not any(p.code in ("budget", "unbought") for p in report.problems)

    chosen, report = plan(1.0)
    if not fits(report):
        low, high = 0.0, 1.0
        for _ in range(30):
            mid = (low + high) / 2
            if fits(plan(mid)[1]):
                low = mid
            else:
                high = mid
        chosen, report = plan(low)
    old = {m.player_id: m.full_wage for m in owned}
    updates = [{"p": m.player_id, "c": club_id, "w": _weekly(m.wage)}
               for m in chosen if m.loan is None and m.wage != old[m.player_id]]
    if updates:
        conn.execute(text("UPDATE contract SET wage_weekly_cents = :w WHERE person_id = :p AND "
                          "club_id = :c AND is_active = 1 AND kind != 'loan'"), updates)


def start_mls(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """MLS's clubs start the season under the rules: a club new to them is set up
    (``_start_club``); every club then has its designations, and the AI clubs (every club, at
    the career's start) fix what doesn't comply. Returns news for the user."""
    clubs = sorted(mls_club_ids(conn, world, meta.season_id))
    if not clubs:
        return []
    fresh = [c for c in clubs if state(conn, c, meta.season_id) is None
             and conn.execute(text("SELECT 1 FROM mls_club_season WHERE club_id = :c LIMIT 1"),
                              {"c": c}).first() is None]
    for club_id in fresh:
        _start_club(conn, world, meta, club_id, day)
    news = []
    for club_id in clubs:
        if state(conn, club_id, meta.season_id) is None:
            continue
        if club_id != meta.user_club_id or club_id in fresh:
            fix_club(conn, world, meta, club_id, day, clubs)
        else:
            raise_to_minimum(conn, world, meta, club_id, day)
            report = club_report(conn, world, meta, club_id, day, money_for(world, meta))
            save_report(conn, meta, club_id, report)
            if not report.compliant:
                news.append(user_problems_news(report))
    charge_dp_fees(conn, world, meta, day)
    return news


def user_problems_news(report: Report) -> str:
    return ("Your roster doesn't comply with MLS's rules: " + " ".join(
        p.text for p in report.problems) + " You can't add players until it does (the MLS "
        "roster page).")


def new_mls_season(conn: Connection, world: World, meta: CareerMeta, old_season: int,
                   day: date) -> list[str]:
    """The season's allocations at the rollover (``meta.season_id`` is the new season): each
    club's GAM, less what last season's buy-downs took and Model 2's that has expired, plus the
    annual allocation (and Model 2's, and the play-off miss's); this season's TAM; its slots
    back to 8; green cards; then the designations and the AI's fixes (``start_mls``)."""
    rules = world.defs.mls
    fig = figures(world)
    missed = _missed_playoffs(conn, world, old_season)
    for r in conn.execute(text("SELECT * FROM mls_club_season WHERE season_id = :s "
                               "ORDER BY club_id"), {"s": old_season}).all():
        if state(conn, int(r.club_id), meta.season_id) is not None:
            continue
        spent = int(r.gam_committed_cents)
        from_expiring = min(spent, int(r.gam_expiring_cents))
        carried = int(r.gam_cents) - (spent - from_expiring)
        _new_state(conn, world, meta, int(r.club_id), int(r.roster_model), carried, day)
        if spent:
            conn.execute(text("INSERT INTO mls_gam (club_id, season_id, date, kind, "
                              "amount_cents) VALUES (:c, :s, :d, 'spent', :a)"),
                         {"c": r.club_id, "s": old_season, "d": day.isoformat(), "a": -spent})
        left = int(r.gam_expiring_cents) - from_expiring
        if left:
            conn.execute(text("INSERT INTO mls_gam (club_id, season_id, date, kind, "
                              "amount_cents) VALUES (:c, :s, :d, 'expired', :a)"),
                         {"c": r.club_id, "s": old_season, "d": day.isoformat(), "a": -left})
        if int(r.club_id) in missed and rules.gam.missed_playoffs:
            _gam(conn, meta, int(r.club_id), "allocation", fig.c(rules.gam.missed_playoffs), day)
    _green_cards(conn, world, meta)
    return start_mls(conn, world, meta, day)


def _missed_playoffs(conn: Connection, world: World, season_id: int) -> set[int]:
    return {int(r.club_id) for r in conn.execute(text(
        "SELECT f.club_id FROM league_final f JOIN competition c ON c.id = f.competition_id "
        "WHERE c.key = :k AND f.season_id = :s AND f.outcome IS NULL"),
        {"k": world.defs.mls.league, "s": season_id})}


def _green_cards(conn: Connection, world: World, meta: CareerMeta) -> None:
    """Foreign players on MLS rosters for ``green_card_seasons`` seasons become domestic."""
    conn.execute(text("UPDATE mls_player SET green_card = 1 WHERE green_card = 0 AND "
                      "since_season IS NOT NULL AND :s - since_season >= :n"),
                 {"s": meta.season_id, "n": world.defs.mls.green_card_seasons})


def mls_month(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """The first of each month: a save that has no MLS season yet takes up the rules (one from
    before them); AI clubs fix what has slipped (a sale that left an empty slot, say)."""
    clubs = sorted(mls_club_ids(conn, world, meta.season_id))
    if not clubs:
        return []
    if any(state(conn, c, meta.season_id) is None for c in clubs):
        return start_mls(conn, world, meta, day)
    for club_id in clubs:
        if club_id == meta.user_club_id:
            save_report(conn, meta, club_id, club_report(conn, world, meta, club_id, day))
        else:
            fix_club(conn, world, meta, club_id, day, clubs)
    charge_dp_fees(conn, world, meta, day)
    return []


# --- the user's choices ------------------------------------------------------------------------


def set_designation(conn: Connection, world: World, meta: CareerMeta, day: date,
                    player_id: int, designation: str, slot: str | None = None) -> Report:
    """The user designates one of their players (DP, U22, senior: a TAM buy-down, Homegrown,
    supplemental, Generation adidas), on a roster. Refused when he can't have it, or when it
    would break a rule the roster keeps now."""
    club_id = _user_club(conn, meta)
    fig = figures(world)
    money = money_for(world, meta)
    current = club_report(conn, world, meta, club_id, day, money)
    mine = next((m for m in current.members if m.player_id == player_id), None)
    if mine is None:
        raise RosterRefused("He isn't on your roster.")
    fixed = {DP: SENIOR, U22: SENIOR, SENIOR: SENIOR, SUPPLEMENTAL: SUPPLEMENTAL, GA: SUPPLEMENTAL}
    slot = slot or fixed.get(designation, mine.slot)
    reason = not_allowed(fig, mine, designation, slot)
    if reason is not None:
        raise RosterRefused(reason)
    club = club_rules(conn, world, club_id, meta.season_id)
    trial = [replace(m, designation=designation, slot=slot) if m.player_id == player_id else m
             for m in current.members]
    after = assess(fig, club, trial, money)
    fresh = new_problems(assess(fig, club, current.members, money), after)
    if fresh:
        raise RosterRefused(fresh[0].refusal + ".")
    save_report(conn, meta, club_id, after)
    charge_dp_fees(conn, world, meta, day)
    return after


def set_roster_model(conn: Connection, world: World, meta: CareerMeta, day: date,
                     model: int) -> Report:
    """The user's roster model (1: three DPs and three U22 players; 2: two DPs, four U22
    players and $2M more GAM for the season), chosen before their club's first league match."""
    club_id = _user_club(conn, meta)
    rules = world.defs.mls
    fig = figures(world)
    if model not in rules.roster_models:
        raise RosterRefused("There's no such roster model.")
    row = state(conn, club_id, meta.season_id)
    assert row is not None
    if int(row.roster_model) == model:
        return club_report(conn, world, meta, club_id, day, money_for(world, meta))
    played: int = conn.execute(text(
        "SELECT COUNT(*) FROM fixture f JOIN competition c ON c.id = f.competition_id "
        "WHERE c.key = :k AND f.season_id = :s AND f.stage = 'league' AND f.status = 'played' "
        "AND :c IN (f.home_club_id, f.away_club_id)"),
        {"k": rules.league, "s": meta.season_id, "c": club_id}).scalar_one()
    if played:
        raise RosterRefused("The roster model is chosen before the season's first match.")
    money = money_for(world, meta)
    current = club_report(conn, world, meta, club_id, day, money)
    old_extra = fig.c(rules.roster_models[int(row.roster_model)].extra_gam)
    new_extra = fig.c(rules.roster_models[model].extra_gam)
    expiring = max(0, int(row.gam_expiring_cents) - old_extra) + new_extra
    club = replace(club_rules(conn, world, club_id, meta.season_id), model=model,
                   gam=int(row.gam_cents) + expiring)
    after = assess(fig, club, current.members, money)
    fresh = new_problems(assess(fig, club_rules(conn, world, club_id, meta.season_id),
                                current.members, money), after)
    if fresh:
        raise RosterRefused(fresh[0].refusal + ".")
    conn.execute(text("UPDATE mls_club_season SET roster_model = :m, gam_expiring_cents = :e "
                      "WHERE club_id = :c AND season_id = :s"),
                 {"m": model, "e": expiring, "c": club_id, "s": meta.season_id})
    conn.execute(text("INSERT INTO mls_gam (club_id, season_id, date, kind, amount_cents) "
                      "VALUES (:c, :s, :d, 'model', :a)"),
                 {"c": club_id, "s": meta.season_id, "d": day.isoformat(),
                  "a": expiring - int(row.gam_expiring_cents)})
    report = club_report(conn, world, meta, club_id, day, money)
    save_report(conn, meta, club_id, report)
    return report


def buy_international_slot(conn: Connection, world: World, meta: CareerMeta, day: date,
                           seller: int) -> Report:
    """The user buys an international slot for the season from an MLS club with one to spare,
    at the AI's price in GAM."""
    club_id = _user_club(conn, meta)
    rules = world.defs.mls
    fig = figures(world)
    money = money_for(world, meta)
    if seller == club_id or not under_rules(conn, seller, meta.season_id):
        raise RosterRefused("Slots are bought from another MLS club.")
    price = fig.c(rules.slot_price_gam)
    if gam_held(conn, club_id, meta.season_id) < price:
        raise RosterRefused(f"An international slot costs {money(price)} of GAM.")
    row = state(conn, seller, meta.season_id)
    assert row is not None
    members, _ = load_members(conn, world, meta, seller, day)
    free = int(row.international_slots) - sum(1 for m in members if m.international)
    if free <= rules.ai.spare_slots_kept:
        raise RosterRefused("They have no international slot to spare.")
    current = club_report(conn, world, meta, club_id, day, money)
    club = club_rules(conn, world, club_id, meta.season_id)
    after = assess(fig, replace(club, gam=max(0, club.gam - price),
                                international_slots=club.international_slots + 1),
                   current.members, money)
    fresh = new_problems(assess(fig, club, current.members, money), after)
    if fresh:
        raise RosterRefused(fresh[0].refusal + ".")
    trade_slot(conn, meta, seller, club_id, price, day)
    report = club_report(conn, world, meta, club_id, day, money)
    save_report(conn, meta, club_id, report)
    return report


def _user_club(conn: Connection, meta: CareerMeta) -> int:
    if meta.user_club_id is None or not under_rules(conn, meta.user_club_id, meta.season_id):
        raise RosterRefused("Your club doesn't play under MLS's roster rules.")
    return meta.user_club_id
