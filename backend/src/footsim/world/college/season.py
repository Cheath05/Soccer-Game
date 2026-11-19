"""The NCAA season, inside the game's July-June season (data/config/college/rules.yaml).

- **Regular season** (late August to early November): each conference a single round robin, the
  rest non-conference games (competitions/college.py). Games can end level. Fixtures: stage
  ``college``, a round per match day.
- **Conference tournaments** (early to mid November): the conference table's top teams (the
  table counts conference games only), single matches at the higher seed, overtime then
  penalties. Stage ``CT:<conference>``, the tie the bracket match's number. A conference without
  a tournament sends its table's winner.
- **The NCAA tournament:** 48 teams, the conference champions (automatic bids) and the best of the
  rest by the RPI (at-large bids), the top 16 by the RPI seeded with byes. Single matches at the
  higher seed, the College Cup (semi-finals and final) at a neutral ground in December. Stage
  ``NCAA``. Who is in each bracket, at which seed, is in ``college_entry``.
- **Titles** go in ``league_title`` under the NCAA's competition: each conference's regular
  season (an award, or its championship when it has no tournament), its tournament, and the
  national title. After the final the draft pool is declared (world/college/draft.py).

Every match is played by the fast engine like any other (career.py's day of fixtures)."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Connection, Row, func, select, text

from footsim.competitions.bracket import BYE, champion, matches_in, rounds_for, sides
from footsim.competitions.college import Game, ranked, regular_season, rpi
from footsim.competitions.standings import Result, TableRow, league_table
from footsim.core.rng import derive_rng, derive_seed
from footsim.defs.college import CollegeDef, on
from footsim.match.report import Decider
from footsim.persistence.schema import (
    college_entry,
    college_team,
    competition,
    fixture,
    league_title,
    season,
)
from footsim.world.college.common import NCAA, REGULAR, conference_event
from footsim.world.college.draft import declare_prospects, release_undrafted
from footsim.world.college.recruiting import ensure_recruiting
from footsim.world.college.roster import ensure_college
from footsim.world.context import World
from footsim.world.meta import CareerMeta

NATIONAL_TITLE = "NCAA Championship"


def college_competition(conn: Connection, world: World) -> int | None:
    """The NCAA's competition id, or None in a save without the college game yet."""
    found = conn.execute(select(competition.c.id).where(
        competition.c.key == world.defs.college.rules.key)).scalar()
    return int(found) if found is not None else None


def _season_start(conn: Connection, season_id: int) -> date:
    return date.fromisoformat(str(conn.execute(select(season.c.start_date).where(
        season.c.id == season_id)).scalar_one()))


def conference_teams(conn: Connection, college: CollegeDef) -> dict[str, list[int]]:
    """Each conference's clubs (by id), in the order of the programs file."""
    by_key: dict[str, list[int]] = defaultdict(list)
    for r in conn.execute(select(college_team.c.club_id, college_team.c.conference)
                          .order_by(college_team.c.club_id)):
        by_key[str(r.conference)].append(int(r.club_id))
    return {key: by_key[key] for key in college.conferences if by_key.get(key)}


def create_college_fixtures(conn: Connection, world: World, meta: CareerMeta, season_id: int,
                            start: date) -> list[str]:
    """The season's regular-season fixtures (the college world first, if the save lacks it).
    Returns news."""
    news = ensure_college(conn, world, meta, season_id, start)
    news += ensure_recruiting(conn, world, meta, season_id, start)
    comp = college_competition(conn, world)
    if comp is None or conn.execute(select(fixture.c.id).where(
            fixture.c.season_id == season_id, fixture.c.competition_id == comp)).first():
        return news
    rules = world.defs.college.rules.regular_season
    teams = conference_teams(conn, world.defs.college)
    days = regular_season(list(teams.values()), rules.matches, rules.slots,
                          derive_rng(meta.seed, "college-fixtures", season_id))
    first, last = on(rules.start, start), on(rules.end, start)
    span = (last - first).days
    rows = []
    for k, games in enumerate(days):
        day = first + timedelta(days=round(k * span / max(1, len(days) - 1)))
        rows += [{"season_id": season_id, "competition_id": comp, "stage": REGULAR,
                  "round": k + 1, "date": day.isoformat(), "home_club_id": home,
                  "away_club_id": away, "neutral": 0, "status": "scheduled"}
                 for home, away in games]
    if rows:
        conn.execute(fixture.insert(), rows)
    return news


def college_decider(world: World, stage: str) -> Decider | None:
    """Overtime then penalties in the tournaments; a regular-season game can end level."""
    if stage == REGULAR:
        return None
    rules = world.defs.college.rules
    event = rules.ncaa if stage == NCAA else rules.conference_tournament
    return Decider(extra_time=event.extra_time, penalties=event.penalties)


# --- tables ---------------------------------------------------------------------------------


def _results(conn: Connection, comp: int, season_id: int, stage: str | None = None
             ) -> list[Row[Any]]:
    query = select(fixture).where(fixture.c.season_id == season_id,
                                  fixture.c.competition_id == comp,
                                  fixture.c.status == "played")
    if stage is not None:
        query = query.where(fixture.c.stage == stage)
    return list(conn.execute(query.order_by(fixture.c.id)))


@dataclass
class Record:
    """A team's record over every college game of a season (regular season, conference
    tournament and NCAA tournament). A game settled on penalties counts as a draw."""

    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0

    @property
    def played(self) -> int:
        return self.won + self.drawn + self.lost


def overall_records(conn: Connection, world: World, season_id: int) -> dict[int, Record]:
    """Every team's overall record this season so far."""
    comp = college_competition(conn, world)
    found: dict[int, Record] = defaultdict(Record)
    if comp is None:
        return found
    for r in _results(conn, comp, season_id):
        for club, scored, conceded in ((r.home_club_id, r.home_goals, r.away_goals),
                                       (r.away_club_id, r.away_goals, r.home_goals)):
            rec = found[int(club)]
            rec.goals_for += int(scored)
            rec.goals_against += int(conceded)
            if scored > conceded:
                rec.won += 1
            elif scored < conceded:
                rec.lost += 1
            else:
                rec.drawn += 1
    return found


def conference_tables(conn: Connection, world: World, meta: CareerMeta, season_id: int
                      ) -> dict[str, list[TableRow]]:
    """Every conference's table this season: its conference games only."""
    comp = college_competition(conn, world)
    if comp is None:
        return {}
    rules = world.defs.college.rules
    games = [Result(r.home_club_id, r.away_club_id, r.home_goals, r.away_goals)
             for r in _results(conn, comp, season_id, REGULAR)]
    tables = {}
    for key, clubs in conference_teams(conn, world.defs.college).items():
        members = set(clubs)
        own = [g for g in games if g.home in members and g.away in members]
        tables[key] = league_table(clubs, own, rules.points, rules.tiebreakers,
                                   derive_seed(meta.seed, "college-lots", season_id, key))
    return tables


def _score(r: Row[Any], draw: float) -> float:
    """The home side's result for the ranking: a shoot-out counts as a draw."""
    if r.home_goals > r.away_goals:
        return 1.0
    if r.home_goals < r.away_goals:
        return 0.0
    return draw


def rankings(conn: Connection, world: World, season_id: int) -> dict[int, float]:
    """Every team's RPI from this season's games so far."""
    comp = college_competition(conn, world)
    if comp is None:
        return {}
    rules = world.defs.college.rules.ranking
    return rpi([Game(r.home_club_id, r.away_club_id, _score(r, rules.draw_value))
                for r in _results(conn, comp, season_id)], rules.weights)


# --- titles and brackets --------------------------------------------------------------------


def _title(conn: Connection, comp: int, season_id: int, title: str, club_id: int, kind: str,
           phase: str | None, day: date) -> bool:
    """A title won; False if it was recorded already."""
    if conn.execute(select(league_title.c.club_id).where(
            league_title.c.season_id == season_id, league_title.c.competition_id == comp,
            league_title.c.title == title)).first() is not None:
        return False
    conn.execute(league_title.insert().values(
        season_id=season_id, competition_id=comp, title=title, club_id=club_id, kind=kind,
        phase=phase, won_on=day.isoformat()))
    return True


def _club_name(conn: Connection, club_id: int) -> str:
    return str(conn.execute(text("SELECT name FROM club WHERE id = :c"),
                            {"c": club_id}).scalar_one())


def entries(conn: Connection, season_id: int, event: str) -> dict[int, int]:
    """An event's bracket: seed -> club."""
    return {int(r.seed): int(r.club_id) for r in conn.execute(select(college_entry).where(
        college_entry.c.season_id == season_id, college_entry.c.event == event))}


def _knockout_winner(r: Row[Any]) -> int | None:
    if r.status != "played":
        return None
    if r.home_goals != r.away_goals:
        return int(r.home_club_id if r.home_goals > r.away_goals else r.away_club_id)
    if r.home_pens is None:
        return None
    return int(r.home_club_id if r.home_pens > r.away_pens else r.away_club_id)


@dataclass(frozen=True)
class BracketMatch:
    round: int
    index: int
    seed_a: int | None
    seed_b: int | None  # BYE (0) for a first-round bye
    fixture: Row[Any] | None
    winner_seed: int | None


def bracket(conn: Connection, comp: int, season_id: int, event: str
            ) -> tuple[dict[int, int], list[BracketMatch]]:
    """An event's seeds (seed -> club) and every match of its bracket as it stands."""
    seeds = entries(conn, season_id, event)
    seed_of = {c: s for s, c in seeds.items()}
    played: dict[tuple[int, int], Row[Any]] = {}
    for r in conn.execute(select(fixture).where(
            fixture.c.season_id == season_id, fixture.c.competition_id == comp,
            fixture.c.stage == event)):
        played[(int(r.round), int(r.tie))] = r
    winners = {}
    for key, r in played.items():
        won = _knockout_winner(r)
        if won is not None:
            winners[key] = seed_of[won]
    matches = []
    n = len(seeds)
    for rnd in range(rounds_for(n)):
        for index in range(matches_in(n, rnd)):
            a, b = sides(n, rnd, index, winners)
            through = a if rnd == 0 and b == BYE else winners.get((rnd, index))
            matches.append(BracketMatch(rnd, index, a, b, played.get((rnd, index)), through))
    return seeds, matches


def _advance(conn: Connection, comp: int, season_id: int, event: str, dates: list[date],
             neutral_from: int | None, day: date) -> int | None:
    """Schedule the event's matches whose sides are known; its champion's club once decided."""
    seeds, matches = bracket(conn, comp, season_id, event)
    n = len(seeds)
    total = rounds_for(n)
    rows = []
    for m in matches:
        if m.fixture is not None or m.seed_a is None or m.seed_b is None or m.seed_b == BYE:
            continue
        when = max(dates[len(dates) - total + m.round], day + timedelta(days=1))
        neutral = neutral_from is not None and m.round >= neutral_from
        rows.append({"season_id": season_id, "competition_id": comp, "stage": event,
                     "round": m.round, "tie": str(m.index), "leg": None,
                     "date": when.isoformat(), "home_club_id": seeds[m.seed_a],
                     "away_club_id": seeds[m.seed_b], "neutral": int(neutral),
                     "status": "scheduled"})
    if rows:
        conn.execute(fixture.insert(), rows)
    winners = {(m.round, m.index): m.winner_seed for m in matches if m.winner_seed is not None}
    top = champion(n, winners)
    return seeds[top] if top is not None else None


def _seed(conn: Connection, season_id: int, event: str, clubs: list[int],
          bids: dict[int, str] | None = None, ratings: dict[int, float] | None = None,
          ranks: dict[int, int] | None = None) -> None:
    conn.execute(college_entry.insert(), [
        {"season_id": season_id, "event": event, "club_id": c, "seed": k,
         "bid": (bids or {}).get(c), "rank": (ranks or {}).get(c),
         "rating": (ratings or {}).get(c)}
        for k, c in enumerate(clubs, start=1)])


def _start_conferences(conn: Connection, world: World, meta: CareerMeta, comp: int,
                       day: date) -> list[str]:
    """The regular season is over: each conference's table champion, and its tournament's
    field."""
    college = world.defs.college
    news = []
    for key, table in conference_tables(conn, world, meta, meta.season_id).items():
        conference = college.conferences[key]
        top = table[0].club_id
        has_tournament = conference.tournament >= 2
        _title(conn, comp, meta.season_id, f"{conference.short_name} regular season", top,
               "award" if has_tournament else "champion", key, day)
        if has_tournament:
            _seed(conn, meta.season_id, conference_event(key),
                  [r.club_id for r in table[:conference.tournament]])
        news.append(f"{_club_name(conn, top)} win the {conference.short_name} regular season.")
    return [" ".join(news)] if news else []


def _conference_champions(conn: Connection, comp: int, season_id: int) -> dict[str, int]:
    """The conferences decided so far: their champion (tournament winner, or the table's)."""
    return {str(r.phase): int(r.club_id) for r in conn.execute(select(league_title).where(
        league_title.c.season_id == season_id, league_title.c.competition_id == comp,
        league_title.c.kind == "champion", league_title.c.phase.is_not(None),
        league_title.c.phase != NCAA))}


def select_field(conn: Connection, world: World, season_id: int, comp: int) -> list[str]:
    """The NCAA tournament's field: every conference champion with an automatic bid, then the
    best of the rest by the RPI; seeded by the RPI. Returns news."""
    college = world.defs.college
    rules = college.rules.ncaa
    champions = _conference_champions(conn, comp, season_id)
    ratings = rankings(conn, world, season_id)
    order = ranked(ratings)
    rank_of = {c: k for k, c in enumerate(order, start=1)}
    auto = {champions[k] for k, c in college.conferences.items() if c.auto_bid and k in champions}
    field = set(auto)
    for club_id in order:
        if len(field) >= rules.teams:
            break
        field.add(club_id)
    seeded = sorted(field, key=lambda c: (rank_of.get(c, len(order) + 1), c))
    bids = {c: "auto" if c in auto else "at_large" for c in seeded}
    _seed(conn, season_id, NCAA, seeded, bids, ratings, rank_of)
    top = _club_name(conn, seeded[0])
    return [f"The NCAA tournament's field of {len(seeded)} is out: {len(auto)} conference "
            f"champions and {len(seeded) - len(auto)} at-large teams. {top} are the top seed."]


def progress_college(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """A day of the college season: tables, tournaments, the NCAA field and bracket, titles,
    the draft pool and the release of the undrafted. Returns news."""
    comp = college_competition(conn, world)
    if comp is None:
        return []
    college = world.defs.college
    start = _season_start(conn, meta.season_id)
    news: list[str] = []
    if day >= on(college.rules.draft.release, start):
        news += release_undrafted(conn, meta, day)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for r in conn.execute(select(fixture.c.stage, fixture.c.status, func.count()).where(
            fixture.c.season_id == meta.season_id, fixture.c.competition_id == comp)
            .group_by(fixture.c.stage, fixture.c.status)):
        counts[(str(r[0]), str(r[1]))] = int(r[2])
    if not counts.get((REGULAR, "played")) or counts.get((REGULAR, "scheduled")):
        return news  # no college season this year, or its regular season is still on
    if conn.execute(select(league_title.c.club_id).where(
            league_title.c.season_id == meta.season_id, league_title.c.competition_id == comp,
            league_title.c.title == NATIONAL_TITLE)).first() is not None:
        return news  # the season is over
    started = conn.execute(select(college_entry.c.event).where(
        college_entry.c.season_id == meta.season_id).limit(1)).first() is not None
    if not started and not _conference_champions(conn, comp, meta.season_id):
        news += _start_conferences(conn, world, meta, comp, day)
    dates = [on(d, start) for d in college.rules.conference_tournament.rounds]
    champions = _conference_champions(conn, comp, meta.season_id)
    for key, conference in college.conferences.items():
        if key in champions or conference.tournament < 2:
            continue
        won = _advance(conn, comp, meta.season_id, conference_event(key), dates, None, day)
        if won is not None and _title(conn, comp, meta.season_id,
                                      f"{conference.short_name} Tournament", won, "champion",
                                      key, day):
            news.append(f"{_club_name(conn, won)} win the {conference.short_name} Tournament.")
    champions = _conference_champions(conn, comp, meta.season_id)
    ncaa = college.rules.ncaa
    if not entries(conn, meta.season_id, NCAA):
        if set(conference_teams(conn, college)) - set(champions) or day < on(ncaa.selection,
                                                                             start):
            return news
        news += select_field(conn, world, meta.season_id, comp)
    won = _advance(conn, comp, meta.season_id, NCAA, [on(d, start) for d in ncaa.rounds],
                   ncaa.neutral_from, day)
    if won is not None and _title(conn, comp, meta.season_id, NATIONAL_TITLE, won, "champion",
                                  NCAA, day):
        news.append(f"{_club_name(conn, won)} win the College Cup: they are the NCAA champions.")
        news += declare_prospects(conn, world, meta, meta.season_id, day)
    return news
