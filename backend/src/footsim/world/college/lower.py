"""NCAA Divisions II and III (W9e): real schools in their conferences, played with quick
results (data/config/college/lower.yaml, ncaa_d2.yaml, ncaa_d3.yaml).

Each division is a competition of type ``college_lower`` whose programs live in ``lower_team``
and players in ``lower_player``, apart from D-I's tables, so D-I's recruiting, rankings, draft and
program builder never see them; the professional game leaves them out like D-I's
(college/common.py). A season: each team plays its conference once and fills the rest with
non-conference games (as D-I); the table's top takes its conference title and the automatic bid;
the best of the rest by points a game fill the national tournament's field, seeded the same way;
single matches, the higher seed at home until the late rounds, extra time and penalties. At the
rollover seniors leave the game, the rest move up a class, and rosters refill with freshmen.
Nobody coaches these programs: they are the game's."""

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import Connection, select, text, update

from footsim.competitions.college import regular_season
from footsim.competitions.standings import Result, TableRow, league_table
from footsim.core.rng import derive_rng, derive_seed
from footsim.defs.college import DivisionDef, LowerDef, on
from footsim.persistence.schema import (
    club,
    competition,
    contract,
    fixture,
    lower_player,
    lower_team,
    player,
    recruit,
    tactic,
)
from footsim.world.college.common import LOWER_PREFIX, LOWER_REGULAR, LOWER_TYPE, is_college_club
from footsim.world.college.roster import RecruitPerson, _age, _draw_class, _Maker, _player_overall
from footsim.world.college.season import (
    _advance,
    _club_name,
    _results,
    _season_start,
    _seed,
    _title,
    entries,
)
from footsim.world.context import World, default_instructions
from footsim.world.meta import CareerMeta, bump_players_epoch

NATIONAL_TITLE = "national championship"  # a division's title: "NCAA D-II national championship"


def rules(world: World) -> LowerDef | None:
    return world.defs.college.lower


def event(division: int) -> str:
    """A division's national tournament's stage and event: LOWER2, LOWER3."""
    return f"{LOWER_PREFIX}{division}"


def competitions(conn: Connection, world: World) -> dict[int, int]:
    """Each division's competition id, once the career has the divisions."""
    lower = rules(world)
    if lower is None:
        return {}
    ids = {str(r.key): int(r.id) for r in conn.execute(
        select(competition.c.key, competition.c.id).where(competition.c.type == LOWER_TYPE))}
    return {div: ids[d.key] for div, d in lower.divisions.items() if d.key in ids}


def ensure_lower(conn: Connection, world: World, meta: CareerMeta, season_id: int, day: date
                 ) -> list[str]:
    """Divisions II and III, if the save hasn't got them: their competitions, programs and
    rosters. Returns news."""
    lower = rules(world)
    if lower is None or conn.execute(select(lower_team.c.club_id).limit(1)).first() is not None:
        return []
    # Only a college coach's career has them: they're where D-I finds portal players, and
    # nothing in a professional career would use them.
    if not is_college_club(conn, meta.user_club_id):
        return []
    maker = _Maker(conn, world, meta, day)
    college = world.defs.college.rules
    taken = {str(r.name) for r in conn.execute(select(club.c.name))}
    instructions = json.dumps(default_instructions(world.defs))
    programs = 0
    for div, d in sorted(lower.divisions.items()):
        conn.execute(competition.insert().values(
            key=d.key, name=d.name, short_name=d.short_name, nation_id=maker.home,
            type=LOWER_TYPE, tier=None, sim_level="simulated"))
        for key, conference in d.conferences.items():
            for team in conference.teams:
                rng = derive_rng(meta.seed, "lower-program", div, team.name)
                level = d.level_by_tier[team.tier] + float(rng.normal(0.0, lower.level_sd))
                name = team.name if team.name not in taken else f"{team.name} ({d.short_name})"
                taken.add(name)
                inserted = conn.execute(club.insert().values(
                    name=name, nation_id=maker.home, source_league=f"footsim:{d.key}",
                    reputation=d.reputation, stadium_name=None, stadium_capacity=None))
                assert inserted.inserted_primary_key is not None
                club_id = int(inserted.inserted_primary_key[0])
                conn.execute(lower_team.insert().values(
                    club_id=club_id, division=div, conference=key, tier=team.tier,
                    level=round(level, 2)))
                conn.execute(tactic.insert().values(
                    club_id=club_id, formation=college.formation, roles="{}", lineup=None,
                    instructions=instructions))
                for position in college.roster.shape[:lower.roster_size]:
                    year = _draw_class(college, rng)
                    maker.make(club_id, d.reputation, position, year,
                               _age(college, college.roster.age[year], college.roster.age_sd,
                                    rng),
                               _player_overall(college, level, year, rng), season_id,
                               lower=True)
                programs += 1
    maker.rows.write(conn, with_state=True)
    bump_players_epoch(conn)
    return [f"NCAA Divisions II and III: {programs} more college programs, where the high-school "
            "seniors D-I doesn't sign go on developing. Their best can enter the transfer portal "
            "to D-I after their season."]


def _conferences(conn: Connection, division: int) -> dict[str, list[int]]:
    found: dict[str, list[int]] = defaultdict(list)
    for r in conn.execute(select(lower_team.c.club_id, lower_team.c.conference).where(
            lower_team.c.division == division).order_by(lower_team.c.club_id)):
        found[str(r.conference)].append(int(r.club_id))
    return dict(found)


def _independent(world: World, division: int, key: str) -> bool:
    lower = rules(world)
    assert lower is not None
    return not lower.divisions[division].conferences[key].auto_bid


def create_lower_fixtures(conn: Connection, world: World, meta: CareerMeta, season_id: int,
                          start: date) -> list[str]:
    """The season's regular-season fixtures in each division (the divisions first, if the save
    lacks them). Returns news."""
    lower = rules(world)
    if lower is None:
        return []
    news = ensure_lower(conn, world, meta, season_id, start)
    comps = competitions(conn, world)
    season_rules = lower.regular_season
    for div, comp in sorted(comps.items()):
        if conn.execute(select(fixture.c.id).where(fixture.c.season_id == season_id,
                                                   fixture.c.competition_id == comp)
                        .limit(1)).first():
            continue
        groups: list[list[int]] = []
        for key, clubs in _conferences(conn, div).items():
            # Independents play only non-conference games: a "conference" of one each.
            groups += [[c] for c in clubs] if _independent(world, div, key) else [clubs]
        days = regular_season(groups, season_rules.matches, season_rules.slots,
                              derive_rng(meta.seed, "lower-fixtures", div, season_id))
        first, last = on(season_rules.start, start), on(season_rules.end, start)
        span = (last - first).days
        rows = []
        for k, games in enumerate(days):
            day = first + timedelta(days=round(k * span / max(1, len(days) - 1)))
            rows += [{"season_id": season_id, "competition_id": comp, "stage": LOWER_REGULAR,
                      "round": k + 1, "date": day.isoformat(), "home_club_id": home,
                      "away_club_id": away, "neutral": 0, "status": "scheduled"}
                     for home, away in games]
        if rows:
            conn.execute(fixture.insert(), rows)
    return news


# --- tables, rankings, titles -------------------------------------------------------------


def conference_tables(conn: Connection, world: World, meta: CareerMeta, division: int,
                      season_id: int) -> dict[str, list[TableRow]]:
    """Each conference's table in ``division``: its conference games only."""
    comp = competitions(conn, world).get(division)
    if comp is None:
        return {}
    college = world.defs.college.rules
    games = [Result(r.home_club_id, r.away_club_id, r.home_goals, r.away_goals)
             for r in _results(conn, comp, season_id, LOWER_REGULAR)]
    tables = {}
    for key, clubs in _conferences(conn, division).items():
        if _independent(world, division, key):
            continue
        members = set(clubs)
        own = [g for g in games if g.home in members and g.away in members]
        tables[key] = league_table(clubs, own, college.points, college.tiebreakers,
                                   derive_seed(meta.seed, "lower-lots", division, season_id, key))
    return tables


@dataclass
class Standing:
    club_id: int
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0

    @property
    def points_a_game(self) -> float:
        return (3 * self.won + self.drawn) / self.played if self.played else 0.0


def records(conn: Connection, world: World, division: int, season_id: int
            ) -> dict[int, Standing]:
    """Every team's record over the division's games this season (a shoot-out is a draw)."""
    comp = competitions(conn, world).get(division)
    found: dict[int, Standing] = {}
    if comp is None:
        return found
    for r in _results(conn, comp, season_id):
        for club_id, scored, conceded in ((r.home_club_id, r.home_goals, r.away_goals),
                                          (r.away_club_id, r.away_goals, r.home_goals)):
            s = found.setdefault(int(club_id), Standing(int(club_id)))
            s.played += 1
            s.goals_for += int(scored)
            s.goals_against += int(conceded)
            if scored > conceded:
                s.won += 1
            elif scored < conceded:
                s.lost += 1
            else:
                s.drawn += 1
    return found


def ranking(conn: Connection, world: World, division: int, season_id: int) -> list[int]:
    """The division's teams best first: points a game, then goal difference a game, goals."""
    found = records(conn, world, division, season_id)
    return sorted(found, key=lambda c: (-found[c].points_a_game,
                                        -(found[c].goals_for - found[c].goals_against)
                                        / max(1, found[c].played),
                                        -found[c].goals_for, c))


def _division_title(d: DivisionDef) -> str:
    return f"{d.short_name} {NATIONAL_TITLE}"


def progress_lower(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """A day of the lower divisions: once the regular season is over, the conference titles and
    the national tournament's field; then its rounds and champion. Returns news (the champions
    only: the rest is on the College page)."""
    lower = rules(world)
    if lower is None:
        return []
    # A save from before the divisions gets them at once (their games start next season), so
    # this December's portal has players to offer.
    news: list[str] = ensure_lower(conn, world, meta, meta.season_id, day)
    news += open_portal(conn, world, meta, day)
    start = _season_start(conn, meta.season_id)
    for div, comp in sorted(competitions(conn, world).items()):
        d = lower.divisions[div]
        left: int = conn.execute(text(
            "SELECT COUNT(*) FROM fixture WHERE season_id = :s AND competition_id = :c AND "
            "stage = :r AND status = 'scheduled'"),
            {"s": meta.season_id, "c": comp, "r": LOWER_REGULAR}).scalar_one()
        played = conn.execute(text(
            "SELECT 1 FROM fixture WHERE season_id = :s AND competition_id = :c AND "
            "status = 'played' LIMIT 1"), {"s": meta.season_id, "c": comp}).first()
        if left or played is None:
            continue
        ev = event(div)
        if not entries(conn, meta.season_id, ev):
            if day < on(d.tournament.selection, start):
                continue
            news += _select_field(conn, world, meta, div, comp, day)
        dates = [on(x, start) for x in d.tournament.rounds]
        won = _advance(conn, comp, meta.season_id, ev, dates, d.tournament.neutral_from, day)
        if won is not None and _title(conn, comp, meta.season_id, _division_title(d), won,
                                      "champion", ev, day):
            news.append(f"{_club_name(conn, won)} are the {d.short_name} national champions.")
    return news


def _select_field(conn: Connection, world: World, meta: CareerMeta, division: int, comp: int,
                  day: date) -> list[str]:
    lower = rules(world)
    assert lower is not None
    d = lower.divisions[division]
    auto = []
    for key, table in conference_tables(conn, world, meta, division, meta.season_id).items():
        if table and table[0].played:
            top = table[0].club_id
            conference = d.conferences[key]
            _title(conn, comp, meta.season_id, f"{conference.short_name} regular season", top,
                   "champion", key, day)
            if conference.auto_bid:
                auto.append(top)
    order = ranking(conn, world, division, meta.season_id)
    rank_of = {c: k for k, c in enumerate(order, start=1)}
    field = list(dict.fromkeys(auto))[:d.tournament.teams]
    for club_id in order:
        if len(field) >= d.tournament.teams:
            break
        if club_id not in field:
            field.append(club_id)
    seeded = sorted(field, key=lambda c: (rank_of.get(c, len(order) + 1), c))
    _seed(conn, meta.season_id, event(division), seeded,
          {c: "auto" if c in auto else "at_large" for c in seeded}, None,
          {c: rank_of.get(c, 0) for c in seeded})
    return []


# --- the rollover -------------------------------------------------------------------------------


def lower_turnover(conn: Connection, world: World, meta: CareerMeta, new_season: int, day: date
                   ) -> list[str]:
    """At the new season's start: seniors leave the game, everyone else moves up a class, and
    each roster refills with freshmen to its size. Returns news."""
    lower = rules(world)
    if lower is None or conn.execute(select(lower_team.c.club_id).limit(1)).first() is None:
        return []
    seniors = [int(r.player_id) for r in conn.execute(
        select(lower_player.c.player_id).where(lower_player.c.class_year >= 4))]
    if seniors:
        conn.execute(update(player).where(player.c.person_id.in_(seniors))
                     .values(retired_on=day.isoformat()))
        conn.execute(update(contract).where(contract.c.person_id.in_(seniors),
                                            contract.c.is_active == 1)
                     .values(is_active=0, end_date=day.isoformat()))
        conn.execute(lower_player.delete().where(lower_player.c.player_id.in_(seniors)))
    conn.execute(text("UPDATE lower_player SET class_year = class_year + 1"))
    placed = place_unsigned(conn, world, meta, new_season, day)
    arrived = refill(conn, world, meta, new_season, day)
    bump_players_epoch(conn)
    return [f"College soccer: {len(seniors)} D-II and D-III seniors graduate; {placed} "
            f"high-school seniors D-I didn't sign join their programs, with {arrived} more "
            "freshmen."]


LOWER_JOINED = "lower"  # a recruit status: unsigned by D-I, he joined a D-II/D-III program


def place_unsigned(conn: Connection, world: World, meta: CareerMeta, season_id: int, day: date
                   ) -> int:
    """The high-school seniors of the class enrolling now whom no D-I program signed join the
    lower divisions as freshmen, keeping who they are and their potential: the hidden gems. The
    best go first, to the strongest programs that have places (D-II's before D-III's).
    Returns how many."""

    from footsim.world.college.recruiting import GONE

    lower = rules(world)
    assert lower is not None
    rows = conn.execute(select(recruit).where(
        recruit.c.class_season == season_id, recruit.c.status == GONE,
        recruit.c.player_id.is_(None), recruit.c.source.is_(None))
        .order_by(recruit.c.grade.desc(), recruit.c.id)).all()
    if not rows:
        return 0
    size: dict[int, int] = defaultdict(int)
    for r in conn.execute(text("SELECT club_id, COUNT(*) AS n FROM lower_player GROUP BY club_id")):
        size[int(r.club_id)] = int(r.n)
    teams = conn.execute(select(lower_team).order_by(lower_team.c.division,
                                                      lower_team.c.level.desc(),
                                                      lower_team.c.club_id)).all()
    places = [(int(t.club_id), int(t.division)) for t in teams
              for _ in range(max(0, lower.roster_size - size[int(t.club_id)]))]
    # Deal the places out a program at a time, strongest first, so each gets a share.
    order: list[tuple[int, int]] = []
    by_team: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for place in places:
        by_team[place[0]].append(place)
    queues = [by_team[int(t.club_id)] for t in teams if by_team[int(t.club_id)]]
    while queues:
        order += [q.pop() for q in queues]
        queues = [q for q in queues if q]
    maker = _Maker(conn, world, meta, day)
    links = []
    for r, (club_id, division) in zip(rows, order, strict=False):
        born = date.fromisoformat(r.birth_date)
        pid = maker.make(club_id, lower.divisions[division].reputation, str(r.position), 1,
                         (day - born).days / 365.25, float(r.overall), season_id,
                         signed=RecruitPerson(str(r.first_name), str(r.last_name),
                                              int(r.nation_id), born, int(r.potential)),
                         lower=True)
        links.append({"id": int(r.id), "p": pid, "c": club_id})
    maker.rows.write(conn, with_state=True)
    if links:
        conn.execute(text(f"UPDATE recruit SET status = '{LOWER_JOINED}', player_id = :p, "
                          "club_id = :c WHERE id = :id"), links)
    return len(links)


def refill(conn: Connection, world: World, meta: CareerMeta, season_id: int, day: date) -> int:
    """Generated freshmen to bring every lower program back to its roster size, the positions it
    lacks first. Returns how many."""
    lower = rules(world)
    assert lower is not None
    college = world.defs.college.rules
    shape = college.roster.shape[:lower.roster_size]
    have: dict[int, list[str]] = defaultdict(list)
    for r in conn.execute(text(
            "SELECT lp.club_id, (SELECT position FROM player_position pp WHERE pp.player_id = "
            "lp.player_id ORDER BY familiarity DESC, position LIMIT 1) AS position "
            "FROM lower_player lp")):
        have[int(r.club_id)].append(str(r.position))
    maker = _Maker(conn, world, meta, day)
    count = 0
    for t in conn.execute(select(lower_team).order_by(lower_team.c.club_id)).all():
        d = lower.divisions[int(t.division)]
        missing = list(shape)
        for pos in have.get(int(t.club_id), []):
            if pos in missing:
                missing.remove(pos)
        need = lower.roster_size - len(have.get(int(t.club_id), []))
        rng = derive_rng(meta.seed, "lower-freshmen", season_id, int(t.club_id))
        for position in (missing + list(shape))[:max(0, need)]:
            maker.make(int(t.club_id), d.reputation, position, 1,
                       _age(college, college.recruiting.age, college.recruiting.age_sd, rng),
                       _player_overall(college, float(t.level), 1, rng), season_id, lower=True)
            count += 1
    maker.rows.write(conn, with_state=True)
    return count


# --- the transfer portal ------------------------------------------------------------------------

PORTAL = "portal"  # a recruit's source: a lower-division player in the transfer portal


def open_portal(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """On the portal's day, the lower divisions' best non-seniors enter it: they join D-I's
    recruiting class (``recruit`` rows with ``source = portal``). Returns news."""
    import json as _json

    import numpy as np

    from footsim.defs.college import DECISION_PARTS
    from footsim.world.college.recruiting import OPEN

    lower = rules(world)
    if lower is None or lower.portal.entrants <= 0:
        return []
    start = _season_start(conn, meta.season_id)
    if day != on(lower.portal.opens, start):
        return []
    class_season = meta.season_id + 1
    if conn.execute(select(recruit.c.id).where(recruit.c.class_season == class_season,
                                               recruit.c.source == PORTAL).limit(1)).first():
        return []
    if conn.execute(select(recruit.c.id).where(recruit.c.class_season == class_season)
                    .limit(1)).first() is None:
        return []  # no D-I class this year (recruiting not in the save yet)
    hs = world.defs.college.recruiting
    overalls = _overalls_now(conn, world)
    rows = conn.execute(text(
        "SELECT lp.player_id, lp.club_id, lp.class_year, pe.first_name, pe.last_name, "
        "pe.nation_id, pe.birth_date, pl.pa_hidden, lt.division, k.name AS school, "
        "(SELECT position FROM player_position pp WHERE pp.player_id = lp.player_id "
        "ORDER BY familiarity DESC, position LIMIT 1) AS position "
        "FROM lower_player lp JOIN person pe ON pe.id = lp.player_id "
        "JOIN player pl ON pl.person_id = lp.player_id JOIN lower_team lt ON lt.club_id = "
        "lp.club_id JOIN club k ON k.id = lp.club_id "
        "WHERE lp.class_year < 4 AND pl.retired_on IS NULL")).all()
    grade = hs.grade
    candidates = []
    for r in rows:
        overall = overalls.get(int(r.player_id))
        if overall is None or overall < lower.portal.min_overall or r.position not in \
                hs.positions:
            continue
        potential = max(int(r.pa_hidden), round(overall))
        public = overall + grade.potential_weight * (potential - overall)
        candidates.append((public, overall, potential, r))
    candidates.sort(key=lambda c: (-c[0], int(c[3].player_id)))
    chosen = candidates[:lower.portal.entrants]
    if not chosen:
        return []
    grades = [float(g) for (g,) in conn.execute(select(recruit.c.grade).where(
        recruit.c.class_season == class_season))]
    states = _school_states(world)
    made = []
    for public, overall, potential, r in chosen:
        rng = derive_rng(meta.seed, "portal", class_season, int(r.player_id))
        rank = 1 + sum(1 for g in grades if g > public)
        priorities = {part: round(float(rng.gamma(hs.decision.priority_shape,
                                                  1.0 / hs.decision.priority_shape)), 3)
                      for part in DECISION_PARTS}
        pace = float(np.clip(rng.normal(1.0, hs.decision.readiness_sd), 0.5, 1.6))
        same: int = conn.execute(text(
            "SELECT COUNT(*) FROM recruit WHERE class_season = :c AND position = :p "
            "AND grade > :g"), {"c": class_season, "p": r.position, "g": public}).scalar_one()
        made.append({
            "class_season": class_season, "first_name": r.first_name,
            "last_name": r.last_name, "nation_id": int(r.nation_id),
            "state": states.get(str(r.school)), "position": str(r.position),
            "birth_date": r.birth_date, "overall": round(overall, 2), "potential": potential,
            "grade": round(public, 3), "stars": next((s for s in (5, 4, 3)
                                                      if rank <= grade.stars[s]), 2),
            "national_rank": rank, "position_rank": int(same) + 1, "state_rank": None,
            "priorities": _json.dumps(priorities | {"pace": round(pace, 3)}),
            "readiness": 0.0, "status": OPEN, "player_id": int(r.player_id),
            "source": PORTAL, "from_club_id": int(r.club_id)})
    conn.execute(recruit.insert(), made)
    best = chosen[0][3]
    return [f"The transfer portal opens: {len(made)} D-II and D-III players want to move up to "
            f"D-I, led by {best.first_name} {best.last_name} ({best.position}, {best.school}). "
            "They're on Recruiting's board: offer them as you would a recruit."]


def _overalls_now(conn: Connection, world: World) -> dict[int, float]:
    """Every lower-division player's overall (his primary position's)."""
    import numpy as np

    from footsim.domain.attributes import ATTRIBUTES

    rows = conn.execute(text(
        "SELECT a.*, (SELECT position FROM player_position pp WHERE pp.player_id = a.player_id "
        "ORDER BY familiarity DESC, position LIMIT 1) AS position FROM player_attr a "
        "JOIN lower_player lp ON lp.player_id = a.player_id ORDER BY a.player_id")).all()
    if not rows:
        return {}
    groups = world.model.group_overalls(
        np.array([[getattr(r, a) for a in ATTRIBUTES] for r in rows], dtype=float))
    return {int(r.player_id): float(groups[world.defs.positions[str(r.position or "CM")]
                                           .group][i]) for i, r in enumerate(rows)}


def _school_states(world: World) -> dict[str, str]:
    """Each lower program's state, by club name, for a portal player's home."""
    lower = rules(world)
    assert lower is not None
    return {t.name: t.state for d in lower.divisions.values()
            for c in d.conferences.values() for t in c.teams}


def move_up(conn: Connection, season_id: int, day: date, player_id: int, club_id: int,
            share: float) -> None:
    """A portal player who signed with a D-I program joins it at the rollover, a class on from
    his lower-division one, on the scholarship he signed for."""
    from footsim.persistence.schema import college_player
    from footsim.world.college.common import COLLEGE_CONTRACT, ENROLLED

    was = conn.execute(select(lower_player.c.class_year).where(
        lower_player.c.player_id == player_id)).scalar()
    class_year = min(4, int(was or 1) + 1)
    conn.execute(lower_player.delete().where(lower_player.c.player_id == player_id))
    conn.execute(update(contract).where(contract.c.person_id == player_id,
                                        contract.c.is_active == 1)
                 .values(is_active=0, end_date=day.isoformat()))
    conn.execute(contract.insert().values(
        person_id=player_id, club_id=club_id, kind=COLLEGE_CONTRACT,
        start_date=day.isoformat(),
        end_date=date(day.year + (4 - class_year) + 1, 6, 30).isoformat(),
        wage_weekly_cents=0, release_clause_cents=None, is_active=1))
    conn.execute(college_player.insert().values(
        player_id=player_id, club_id=club_id, class_year=class_year, status=ENROLLED, ga=0,
        scholarship=share, entered_season=season_id - class_year + 1, declared_season=None,
        left_on=None))


@dataclass
class LowerSeason:
    """A lower-division program's season, for its club page (as D-I's ``TeamSeason``)."""

    division: int
    conference: str  # its key
    row: TableRow | None
    record: Standing
    rank: int | None  # in its division, by points a game
    national: str | None  # its national tournament run, in words
    titles: list[str]


def team_season(conn: Connection, world: World, meta: CareerMeta, club_id: int,
                season_id: int) -> LowerSeason | None:
    from footsim.world.college.season import bracket

    t = conn.execute(select(lower_team).where(lower_team.c.club_id == club_id)).first()
    lower = rules(world)
    if t is None or lower is None:
        return None
    division, key = int(t.division), str(t.conference)
    table = conference_tables(conn, world, meta, division, season_id).get(key, [])
    row = next((r for r in table if r.club_id == club_id and r.played), None)
    order = ranking(conn, world, division, season_id)
    record = records(conn, world, division, season_id).get(club_id, Standing(club_id))
    comp = competitions(conn, world).get(division)
    national = None
    titles = []
    if comp is not None:
        for r in conn.execute(text(
                "SELECT title FROM league_title WHERE season_id = :s AND competition_id = :c "
                "AND club_id = :k ORDER BY won_on"), {"s": season_id, "c": comp, "k": club_id}):
            titles.append(str(r.title))
        seeds, matches = bracket(conn, comp, season_id, event(division))
        seed = next((s for s, c in seeds.items() if c == club_id), None)
        if seed is not None:
            names = lower.divisions[division].tournament.round_names
            total = max(1, max((m.round for m in matches), default=0) + 1)
            mine = [m for m in matches if seed in (m.seed_a, m.seed_b)]
            last = max(mine, key=lambda m: m.round) if mine else None
            name = (names[len(names) - total + last.round] if last is not None else "")
            if last is None or last.winner_seed is None:
                national = "In the national tournament"
            elif last.winner_seed != seed:
                national = f"National tournament: out in the {name}"
            elif last.round == total - 1:
                national = "National champions"
            else:
                national = f"National tournament: through the {name}"
    return LowerSeason(division=division, conference=key, row=row, record=record,
                       rank=order.index(club_id) + 1 if club_id in order else None,
                       national=national, titles=titles)
