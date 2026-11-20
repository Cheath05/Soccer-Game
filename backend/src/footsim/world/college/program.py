"""The NCAA program builder mode (W9d; data/config/college/program.yaml,
docs/plans/w9d-program-builder.md).

A college coach's career can choose it (``CareerMeta.college_mode == "builder"``). Then every
program has money and two facilities, and the rows in ``college_program`` say the mode is on (the
recruiting and development steps read them without the career's settings):

- **A season's money:** on 1 July the athletic department's allocation (by prestige) comes in,
  and the season's scholarships (every enrolled player's share of the cost of attendance), staff
  and facility upkeep go out. Each home game sells tickets (attendance, below); each away game
  costs travel; NCAA tournament games pay each team by round; boosters give after the regular
  season (wins, a conference title) and after the NCAA tournament (wins, the title).
- **Scholarships come out of the money** (the 2025 rules have no cap): a program's class budget,
  in full scholarships, is what recruiting may spend on next season's class. The coach sets it;
  AI programs set what their tier would fund, within what they can afford.
- **Facilities (levels 1-5):** training speeds the program's players' growth; the stadium's
  capacity sets the crowd. A level is paid for when ordered and ready at the next season's start
  if ordered by the spring cutoff, else the season after. Each level has an upkeep.
- **Attendance** is worked out from the state before the game (capacity, prestige, form, the
  visitors, the kind of game), so the match engine's crowd effect (``crowd_scale``) and the
  ticket sales agree.
- **AI programs** keep a reserve and build with the rest, training first (most of them).

Every draw goes through ``derive_rng``; money is in euro cents, from the file's dollars."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Connection, select, text

from footsim.core.rng import derive_rng
from footsim.defs.college import FACILITIES, ProgramBuilderDef, on
from footsim.persistence.schema import (
    club,
    college_facility,
    college_ledger,
    college_program,
    college_team,
    fixture,
    league_title,
)
from footsim.world.college.common import ENROLLED, NCAA, REGULAR, is_college_stage
from footsim.world.college.recruiting import along, season_start
from footsim.world.context import World
from footsim.world.meta import CareerMeta

BUILDER = "builder"
CLASSIC = "classic"


def rules(world: World) -> ProgramBuilderDef:
    return world.defs.college.program


def cents(world: World, dollars: float) -> int:
    """Dollars (the file's) as the game's money: euro cents."""
    per_euro = world.defs.finance.currencies["USD"].per_euro
    return round(dollars / per_euro * 100)


def is_on(conn: Connection) -> bool:
    """Whether the save runs the program builder mode (its programs have money)."""
    return conn.execute(select(college_program.c.club_id).limit(1)).first() is not None


# --- reading the state ------------------------------------------------------------------------


@dataclass
class Facility:
    kind: str
    level: int
    building_to: int | None
    ready_season: int | None


def facilities(conn: Connection) -> dict[int, dict[str, Facility]]:
    found: dict[int, dict[str, Facility]] = defaultdict(dict)
    for r in conn.execute(select(college_facility)):
        found[int(r.club_id)][str(r.kind)] = Facility(
            str(r.kind), int(r.level), r.building_to, r.ready_season)
    return found


def appeal(conn: Connection, world: World) -> dict[int, float]:
    """Each program's facilities as prestige points in recruits' eyes."""
    per = rules(world).appeal_per_level
    return {club_id: per * (sum(f.level for f in kinds.values()) / max(1, len(kinds)) - 1)
            for club_id, kinds in facilities(conn).items()}


def class_budgets(conn: Connection) -> dict[int, float]:
    """Each program's class budget (full scholarships for next season's class)."""
    return {int(r.club_id): float(r.class_budget)
            for r in conn.execute(select(college_program.c.club_id,
                                         college_program.c.class_budget))}


def growth_factors(conn: Connection, world: World) -> dict[int, float]:
    """Each enrolled college player's growth factor from his program's training facilities."""
    growth = rules(world).facilities.training.growth or [0.0] * 5
    levels = {club_id: kinds["training"].level for club_id, kinds in facilities(conn).items()
              if "training" in kinds}
    found: dict[int, float] = {}
    for r in conn.execute(text(f"SELECT player_id, club_id FROM college_player "
                               f"WHERE status = '{ENROLLED}'")):
        level = levels.get(int(r.club_id))
        if level:
            found[int(r.player_id)] = 1.0 + growth[level - 1]
    return found


def _prestige(conn: Connection, world: World) -> dict[int, float]:
    tiers = world.defs.college.recruiting.programs.prestige_by_tier
    return {int(r.club_id): float(r.prestige) if r.prestige is not None else tiers[int(r.tier)]
            for r in conn.execute(select(college_team.c.club_id, college_team.c.tier,
                                         college_team.c.prestige))}


def _post(conn: Connection, club_id: int, season_id: int, day: date, kind: str, amount: int,
          fixture_id: int | None = None) -> None:
    if amount == 0:
        return
    conn.execute(college_ledger.insert().values(
        club_id=club_id, season_id=season_id, date=day.isoformat(), kind=kind,
        amount_cents=amount, fixture_id=fixture_id))
    conn.execute(text("UPDATE college_program SET balance_cents = balance_cents + :a "
                      "WHERE club_id = :c"), {"a": amount, "c": club_id})


# --- attendance and the crowd ----------------------------------------------------------------


@dataclass(frozen=True)
class Crowd:
    attendance: int
    capacity: int

    @property
    def fill(self) -> float:
        return self.attendance / self.capacity if self.capacity else 0.0


def _event(stage: str) -> str:
    if stage == NCAA:
        return "ncaa"
    return "college" if stage == REGULAR else "conference"


def crowd(conn: Connection, world: World, fx: Any) -> Crowd | None:
    """A college home game's crowd, from the state before it; None for a neutral ground, a
    game that isn't a college one, or a save without the builder mode."""
    if fx.neutral or not is_college_stage(str(fx.stage)):
        return None
    stadium = conn.execute(select(college_facility.c.level).where(
        college_facility.c.club_id == fx.home_club_id,
        college_facility.c.kind == "stadium")).scalar()
    if stadium is None:
        return None
    cfg = rules(world)
    tickets = cfg.tickets
    capacity = (cfg.facilities.stadium.capacity or [0] * 5)[int(stadium) - 1]
    prestige = _prestige(conn, world)
    home, away = int(fx.home_club_id), int(fx.away_club_id)
    recent = conn.execute(text(
        "SELECT home_club_id, home_goals, away_goals FROM fixture "
        "WHERE status = 'played' AND date < :d AND (home_club_id = :c OR away_club_id = :c) "
        "AND competition_id = :comp ORDER BY date DESC, id DESC LIMIT :n"),
        {"d": fx.date, "c": home, "comp": fx.competition_id, "n": tickets.form_games}).all()
    form = 0.0
    if recent:
        points = 0.0
        for r in recent:
            mine, theirs = ((r.home_goals, r.away_goals) if int(r.home_club_id) == home
                            else (r.away_goals, r.home_goals))
            points += 1.0 if mine > theirs else 0.5 if mine == theirs else 0.0
        form = tickets.form_weight * (points / len(recent) - 0.5) * 2
    fill = (along(tickets.fill, prestige.get(home, 50.0)) + form
            + tickets.opponent_weight * (prestige.get(away, 50.0) - 50.0) / 50.0
            + tickets.event.get(_event(str(fx.stage)), 0.0))
    fill = min(1.0, max(tickets.min_fill, fill))
    return Crowd(round(capacity * fill), capacity)


def crowd_scale(world: World, seen: Crowd | None) -> float:
    """The home crowd's effect on the away side (1.0: as calibrated on professional crowds)."""
    if seen is None:
        return 1.0
    c = rules(world).crowd
    size = min(1.0, seen.attendance / c.full_crowd) ** c.size_power
    rise = (1 - c.fill_weight) * size + c.fill_weight * size * seen.fill
    return float(min(1.0, c.min_scale + (1 - c.min_scale) * rise))


# --- starting the mode, and each season ---------------------------------------------------------


def _fixed_costs(world: World, tier: int, levels: dict[str, int]) -> float:
    """A season's staff and upkeep, in dollars."""
    cfg = rules(world)
    upkeep = sum(cfg.facilities.of(k).upkeep[lvl - 1] for k, lvl in levels.items())
    return float(cfg.costs.staff[tier] + upkeep)


def ensure_programs(conn: Connection, world: World, meta: CareerMeta, season_id: int,
                    day: date) -> list[str]:
    """Turn the mode on for a save that chose it: every program's money and facilities, then its
    season's opening (allocation and costs). Returns news."""
    if meta.college_mode != BUILDER or is_on(conn):
        return []
    teams = conn.execute(select(college_team.c.club_id, college_team.c.tier)
                         .order_by(college_team.c.club_id)).all()
    if not teams:
        return []
    cfg = rules(world)
    conn.execute(college_program.insert(), [
        {"club_id": int(t.club_id),
         "balance_cents": cents(world, cfg.starting_balance[int(t.tier)]), "class_budget": 0.0}
        for t in teams])
    conn.execute(college_facility.insert(), [
        {"club_id": int(t.club_id), "kind": kind,
         "level": cfg.facilities.start_level[kind][int(t.tier)], "building_to": None,
         "ready_season": None} for t in teams for kind in FACILITIES])
    open_season(conn, world, meta, season_id, day)
    return []


def open_season(conn: Connection, world: World, meta: CareerMeta, season_id: int,
                day: date) -> None:
    """A season's opening for every program: finished building work, the allocation, the
    season's scholarships, staff and upkeep, and next season's class budgets."""
    if not is_on(conn):
        return
    cfg = rules(world)
    conn.execute(text("UPDATE college_facility SET level = building_to, building_to = NULL, "
                      "ready_season = NULL WHERE ready_season IS NOT NULL "
                      "AND ready_season <= :s"), {"s": season_id})
    prestige = _prestige(conn, world)
    tiers = {int(r.club_id): int(r.tier) for r in conn.execute(
        select(college_team.c.club_id, college_team.c.tier))}
    held: dict[int, float] = defaultdict(float)
    for r in conn.execute(text(f"SELECT club_id, SUM(scholarship) AS s FROM college_player "
                               f"WHERE status = '{ENROLLED}' GROUP BY club_id")):
        held[int(r.club_id)] = float(r.s or 0.0)
    built = facilities(conn)
    for club_id in sorted(tiers):
        levels = {k: f.level for k, f in built.get(club_id, {}).items()}
        _post(conn, club_id, season_id, day, "allocation",
              cents(world, along(cfg.allocation, prestige.get(club_id, 50.0))))
        _post(conn, club_id, season_id, day, "scholarships",
              -cents(world, held[club_id] * cfg.costs.scholarship))
        _post(conn, club_id, season_id, day, "staff",
              -cents(world, cfg.costs.staff[tiers[club_id]]))
        upkeep = sum(cfg.facilities.of(k).upkeep[lvl - 1] for k, lvl in levels.items())
        _post(conn, club_id, season_id, day, "upkeep", -cents(world, upkeep))
    set_ai_class_budgets(conn, world, meta, season_id)


def affordable_class(conn: Connection, world: World, club_id: int, season_id: int) -> float:
    """The most the program can set aside for next season's class, in full scholarships: its
    balance and next season's allocation, less next season's staff, upkeep and the returning
    players' scholarships (what it must pay at the next opening); and never more than a full
    scholarship for each place left on next season's roster."""
    from footsim.world.college.recruiting import load_programs

    cfg = rules(world)
    p = load_programs(conn, world, season_id + 1)[club_id]
    balance = int(conn.execute(select(college_program.c.balance_cents).where(
        college_program.c.club_id == club_id)).scalar_one())
    levels = {k: f.level for k, f in facilities(conn).get(club_id, {}).items()}
    per_euro = world.defs.finance.currencies["USD"].per_euro
    dollars = (balance / 100 * per_euro + along(cfg.allocation, p.prestige)
               - _fixed_costs(world, p.tier, levels)
               - p.returning_money * cfg.costs.scholarship)
    places = world.defs.college.recruiting.programs.roster_max - p.returning_count
    return max(0.0, min(float(places), dollars / cfg.costs.scholarship))


def set_ai_class_budgets(conn: Connection, world: World, meta: CareerMeta,
                         season_id: int) -> None:
    """Every program's class budget at a season's opening: what its tier would fund (less the
    returning players'), within what it can afford. A coach changes theirs on the Program page."""
    from footsim.world.college.recruiting import load_programs

    cfg = rules(world)
    funding = world.defs.college.recruiting.programs.funding_by_tier
    step = world.defs.college.recruiting.programs.share_step
    programs = load_programs(conn, world, season_id + 1)
    updates = []
    for club_id, p in sorted(programs.items()):
        want = max(0.0, (funding[p.tier] - p.returning_money) * cfg.ai.class_budget_share)
        budget = min(want, affordable_class(conn, world, club_id, season_id))
        updates.append({"c": club_id, "b": round(int(budget / step) * step, 2)})
    if updates:
        conn.execute(text("UPDATE college_program SET class_budget = :b WHERE club_id = :c"),
                     updates)


# --- the days ----------------------------------------------------------------------------------


def progress_program(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """A day of the program builder: the day's college games' tickets, travel and NCAA payouts,
    the boosters after the regular season and after the NCAA tournament, and on the first of
    each month the AI programs' building. Returns news (for the coach's program)."""
    if not is_on(conn):
        return []
    cfg = rules(world)
    news: list[str] = []
    season_id = meta.season_id
    user = meta.user_club_id
    for fx in conn.execute(select(fixture).where(
            fixture.c.date == day.isoformat(), fixture.c.status == "played",
            fixture.c.season_id == season_id)).all():
        if not is_college_stage(str(fx.stage)):
            continue
        seen = crowd(conn, world, fx)
        if seen is not None:
            level = int(conn.execute(select(college_facility.c.level).where(
                college_facility.c.club_id == fx.home_club_id,
                college_facility.c.kind == "stadium")).scalar_one())
            conn.execute(fixture.update().where(fixture.c.id == fx.id)
                         .values(attendance=seen.attendance))
            _post(conn, int(fx.home_club_id), season_id, day, "tickets",
                  cents(world, seen.attendance * cfg.tickets.price[level]), int(fx.id))
        if not fx.neutral:
            _post(conn, int(fx.away_club_id), season_id, day, "travel",
                  -cents(world, cfg.costs.travel), int(fx.id))
        if str(fx.stage) == NCAA and 0 <= int(fx.round) < len(cfg.ncaa_payout):
            for side in (int(fx.home_club_id), int(fx.away_club_id)):
                _post(conn, side, season_id, day, "ncaa",
                      cents(world, cfg.ncaa_payout[int(fx.round)]), int(fx.id))
    start = season_start(conn, season_id)
    selection = on(world.defs.college.rules.ncaa.selection, start)
    if day == selection:
        news += _boosters(conn, world, meta, day, ncaa=False)
    if _national_title_on(conn, world, season_id, day):
        news += _boosters(conn, world, meta, day, ncaa=True)
    if day.day == 1:
        _ai_build(conn, world, meta, day)
    return [n for n in news if user is not None]


def _national_title_on(conn: Connection, world: World, season_id: int, day: date) -> bool:
    from footsim.world.college.season import NATIONAL_TITLE, college_competition

    comp = college_competition(conn, world)
    return comp is not None and conn.execute(select(league_title.c.club_id).where(
        league_title.c.season_id == season_id, league_title.c.competition_id == comp,
        league_title.c.title == NATIONAL_TITLE,
        league_title.c.won_on == day.isoformat())).first() is not None


def _boosters(conn: Connection, world: World, meta: CareerMeta, day: date, ncaa: bool
              ) -> list[str]:
    """The boosters' gifts: after the regular season (wins, a conference title), or after the
    NCAA tournament (its wins, the title), each scaled by the program's prestige."""
    from footsim.world.college.season import NATIONAL_TITLE, college_competition

    cfg = rules(world).boosters
    comp = college_competition(conn, world)
    if comp is None:
        return []
    season_id = meta.season_id
    prestige = _prestige(conn, world)
    wins: dict[int, int] = defaultdict(int)
    stages = (NCAA,) if ncaa else (REGULAR,)
    for r in conn.execute(select(fixture).where(
            fixture.c.season_id == season_id, fixture.c.competition_id == comp,
            fixture.c.status == "played", fixture.c.stage.in_(stages))):
        home = (r.home_goals, r.home_pens or 0) > (r.away_goals, r.away_pens or 0)
        away = (r.away_goals, r.away_pens or 0) > (r.home_goals, r.home_pens or 0)
        if home:
            wins[int(r.home_club_id)] += 1
        elif away:
            wins[int(r.away_club_id)] += 1
    titles: dict[int, float] = defaultdict(float)
    for r in conn.execute(select(league_title).where(
            league_title.c.season_id == season_id, league_title.c.competition_id == comp)):
        if ncaa and r.title == NATIONAL_TITLE:
            titles[int(r.club_id)] += cfg.national_title
        elif not ncaa and r.title != NATIONAL_TITLE and r.kind in ("award", "champion") \
                and not str(r.title).endswith("Tournament"):
            titles[int(r.club_id)] += cfg.conference_title
    kind = "boosters_ncaa" if ncaa else "boosters"
    news = []
    for club_id in sorted(set(wins) | set(titles)):
        gift = ((cfg.per_ncaa_win if ncaa else cfg.per_win) * wins[club_id]
                + titles[club_id]) * along(cfg.prestige_scale, prestige.get(club_id, 50.0))
        amount = cents(world, gift)
        _post(conn, club_id, season_id, day, kind, amount)
        if club_id == meta.user_club_id and amount:
            news.append(f"Your boosters give ${round(gift):,} "
                        f"after the {'NCAA tournament' if ncaa else 'regular season'}.")
    return news


# --- building -------------------------------------------------------------------------------------


class ProgramError(ValueError):
    """An action the rules refuse, with the reason for the user."""


def ready_season(world: World, conn: Connection, season_id: int, day: date) -> int:
    """When work ordered on ``day`` is ready: next season if by the spring cutoff."""
    cutoff = on(rules(world).facilities.build_cutoff, season_start(conn, season_id))
    return season_id + 1 if day < cutoff else season_id + 2


def upgrade(conn: Connection, world: World, meta: CareerMeta, club_id: int, kind: str,
            day: date) -> int:
    """Order a facility's next level: pay it now; ready at the season returned."""
    if kind not in FACILITIES:
        raise ProgramError(f"No such facility: {kind}.")
    found = facilities(conn).get(club_id, {}).get(kind)
    if found is None:
        raise ProgramError("This program has no facilities (the program builder mode is off).")
    if found.building_to is not None:
        raise ProgramError(f"The {kind} work is already under way.")
    if found.level >= 5:
        raise ProgramError(f"The {kind} is already at its top level.")
    cost = cents(world, rules(world).facilities.of(kind).cost[found.level])
    balance = int(conn.execute(select(college_program.c.balance_cents).where(
        college_program.c.club_id == club_id)).scalar_one())
    if balance < cost:
        raise ProgramError("Not enough money for that yet.")
    ready = ready_season(world, conn, meta.season_id, day)
    _post(conn, club_id, meta.season_id, day, "build", -cost)
    conn.execute(college_facility.update().where(
        college_facility.c.club_id == club_id, college_facility.c.kind == kind).values(
        building_to=found.level + 1, ready_season=ready))
    return ready


def set_class_budget(conn: Connection, world: World, meta: CareerMeta, club_id: int,
                     budget: float) -> None:
    """The coach's class budget for next season's class, in full scholarships: at least what
    his class has already committed, at most what the program can afford."""
    from footsim.world.college.recruiting import load_programs

    step = world.defs.college.recruiting.programs.share_step
    budget = round(round(budget / step) * step, 2)
    p = load_programs(conn, world, meta.season_id + 1)[club_id]
    if budget + 1e-6 < p.class_money:
        raise ProgramError(f"Your class has already committed {p.class_money:.2f} scholarships.")
    most = affordable_class(conn, world, club_id, meta.season_id)
    if budget > most + 1e-6:
        raise ProgramError(f"You can afford at most {most:.2f} scholarships for the class.")
    conn.execute(college_program.update().where(college_program.c.club_id == club_id)
                 .values(class_budget=budget))


def _ai_build(conn: Connection, world: World, meta: CareerMeta, day: date) -> None:
    """On the first of the month, each AI program with money above its reserve orders its next
    facility level (training first for most; some put the stadium first)."""
    cfg = rules(world)
    tiers = {int(r.club_id): int(r.tier) for r in conn.execute(
        select(college_team.c.club_id, college_team.c.tier))}
    balances = {int(r.club_id): int(r.balance_cents) for r in conn.execute(
        select(college_program.c.club_id, college_program.c.balance_cents))}
    built = facilities(conn)
    for club_id in sorted(balances):
        if club_id == meta.user_club_id:
            continue
        kinds = built.get(club_id, {})
        levels = {k: f.level for k, f in kinds.items()}
        reserve = cents(world, _fixed_costs(world, tiers[club_id], levels)
                        * cfg.ai.reserve_seasons)
        order = list(cfg.ai.priority)
        if derive_rng(meta.seed, "program-priority", club_id).random() < 0.3:
            order.reverse()
        for kind in order:
            f = kinds.get(kind)
            if f is None or f.building_to is not None or f.level >= 5:
                continue
            cost = cents(world, cfg.facilities.of(kind).cost[f.level])
            if balances[club_id] - cost >= reserve:
                upgrade(conn, world, meta, club_id, kind, day)
                balances[club_id] -= cost
            break  # one project at a time, in priority order


# --- what the coach sees -------------------------------------------------------------------------


@dataclass
class LedgerLine:
    kind: str
    amount_cents: int


def season_lines(conn: Connection, club_id: int, season_id: int) -> list[LedgerLine]:
    return [LedgerLine(str(r.kind), int(r.total)) for r in conn.execute(text(
        "SELECT kind, SUM(amount_cents) AS total FROM college_ledger WHERE club_id = :c "
        "AND season_id = :s GROUP BY kind ORDER BY kind"), {"c": club_id, "s": season_id})]


def home_crowds(conn: Connection, club_id: int, season_id: int) -> list[Any]:
    return list(conn.execute(text(
        "SELECT f.id, f.date, f.stage, f.attendance, c.name AS opponent FROM fixture f "
        "JOIN club c ON c.id = f.away_club_id WHERE f.home_club_id = :c AND f.season_id = :s "
        "AND f.attendance IS NOT NULL ORDER BY f.date"), {"c": club_id, "s": season_id}))


def balance_of(conn: Connection, club_id: int) -> int:
    return int(conn.execute(select(college_program.c.balance_cents).where(
        college_program.c.club_id == club_id)).scalar_one())


def program_names(conn: Connection) -> dict[int, str]:
    return {int(r.id): str(r.name) for r in conn.execute(
        select(club.c.id, club.c.name).join(college_team, college_team.c.club_id == club.c.id))}
