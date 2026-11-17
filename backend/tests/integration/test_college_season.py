"""US college soccer (W9a): a whole season on the base world. The college world arrives with the
career, its regular season and conference tournaments lead to a 48-team NCAA tournament (the
conference champions and the best of the rest, the top 16 seeded with byes), a champion and a
draft pool; the rollover graduates and recruits. College players never reach the market, and
college programs have no finances or youth intake. Needs the built world."""

import shutil
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from sqlalchemy import Connection, select, text

import footsim.world.market as market
from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.persistence.schema import college_entry, fixture, league_title
from footsim.world.career import advance, initialize_career
from footsim.world.college import draft_pool, turn_pro
from footsim.world.college.common import IN_COLLEGE_SQL, NCAA, conference_event
from footsim.world.college.season import college_competition, conference_tables
from footsim.world.context import get_world
from footsim.world.meta import read_meta
from footsim.world.transfers import Move, MoveRefused, validate_move

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


class _Season:
    def __init__(self, path: Path, after_cup: Path, leaks: list[int], built: int) -> None:
        self.path, self.after_cup, self.leaks, self.built = path, after_cup, leaks, built


@pytest.fixture(scope="module")
def played(tmp_path_factory: pytest.TempPathFactory) -> _Season:
    """A watch-only career: its first season to the day after the College Cup (copied aside),
    then to the end, with every build of the market's players checked for college players."""
    folder = tmp_path_factory.mktemp("college")
    path = folder / "season.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    world = get_world()
    leaks: list[int] = []
    builds = [0]
    original = market._players

    def checked(conn: Connection, *args: Any) -> Any:
        players = original(conn, *args)
        college = {int(r[0]) for r in conn.execute(text(IN_COLLEGE_SQL))}
        leaks.extend(int(i) for i in players.ids if int(i) in college)
        builds[0] += 1
        return players

    patch = pytest.MonkeyPatch()
    patch.setattr(market, "_players", checked)
    try:
        with engine.begin() as conn:
            initialize_career(conn, world, None, None, seed=11)
        with engine.begin() as conn:
            days = (date(2026, 12, 16) - read_meta(conn).current_date).days
            assert advance(conn, world, max_days=days).stop == "limit"
        engine.dispose()
        after_cup = folder / "after_cup.sqlite"
        shutil.copy(path, after_cup)
        engine = open_database(path)
        with engine.begin() as conn:
            assert advance(conn, world, max_days=400).stop == "season_end"
    finally:
        patch.undo()
        engine.dispose()
    return _Season(path, after_cup, leaks, builds[0])


def _conn(path: Path) -> Connection:
    return open_database(path).connect()


def test_the_regular_season_and_the_conferences(played: _Season) -> None:
    world = get_world()
    with _conn(played.after_cup) as conn:
        comp = college_competition(conn, world)
        assert comp is not None
        games = conn.execute(select(fixture).where(
            fixture.c.competition_id == comp, fixture.c.season_id == 1,
            fixture.c.stage == "college")).all()
        assert all(g.status == "played" for g in games)
        assert min(g.date for g in games) == "2026-08-20"
        assert max(g.date for g in games) == "2026-11-04"
        per_team: Counter[int] = Counter()
        for g in games:
            per_team[g.home_club_id] += 1
            per_team[g.away_club_id] += 1
        assert len(per_team) == sum(len(c.teams) for c in world.defs.college.conferences.values())
        assert all(15 <= n <= 17 for n in per_team.values())
        assert any(g.home_goals == g.away_goals for g in games)  # no overtime in the season
        tables = conference_tables(conn, world, read_meta(conn), 1)
        assert set(tables) == set(world.defs.college.conferences)
        for key, table in tables.items():
            size = len(world.defs.college.conferences[key].teams)
            assert all(r.played == size - 1 for r in table)  # a single round robin
        titles = {(r.title, r.kind): r.club_id for r in conn.execute(select(league_title).where(
            league_title.c.competition_id == comp, league_title.c.season_id == 1))}
        for key, conf in world.defs.college.conferences.items():
            regular = titles.get((f"{conf.short_name} regular season",
                                  "award" if conf.tournament >= 2 else "champion"))
            assert regular == tables[key][0].club_id
            if conf.tournament >= 2:
                assert (f"{conf.short_name} Tournament", "champion") in titles
                seeds = conn.execute(select(college_entry).where(
                    college_entry.c.event == conference_event(key))).all()
                assert len(seeds) == conf.tournament
                tournament = conn.execute(select(fixture).where(
                    fixture.c.competition_id == comp,
                    fixture.c.stage == conference_event(key))).all()
                assert len(tournament) == conf.tournament - 1
                assert all(f.home_pens is not None for f in tournament
                           if f.home_goals == f.away_goals)  # a winner every time


def test_the_ncaa_tournament(played: _Season) -> None:
    world = get_world()
    college = world.defs.college
    with _conn(played.after_cup) as conn:
        comp = college_competition(conn, world)
        field = conn.execute(select(college_entry).where(
            college_entry.c.event == NCAA, college_entry.c.season_id == 1)
            .order_by(college_entry.c.seed)).all()
        assert len(field) == 48
        bids = Counter(r.bid for r in field)
        auto = sum(c.auto_bid for c in college.conferences.values())
        assert bids["auto"] == auto and bids["at_large"] == 48 - auto
        champions = {int(r.club_id) for r in conn.execute(select(league_title).where(
            league_title.c.competition_id == comp, league_title.c.kind == "champion",
            league_title.c.phase != NCAA))}
        assert {r.club_id for r in field if r.bid == "auto"} == champions
        # At-large teams: the best by the RPI of those without an automatic bid.
        at_large = [r.rank for r in field if r.bid == "at_large"]
        out = conn.execute(text("SELECT COUNT(*) FROM college_team WHERE club_id NOT IN "
                                "(SELECT club_id FROM college_entry WHERE event = 'NCAA')"))
        assert out.scalar_one() == sum(len(c.teams) for c in college.conferences.values()) - 48
        assert max(at_large) <= 48  # the best of the rest: none ranked below the field's size
        # Seeds by the RPI; the top 16 have byes into the second round.
        assert [r.rank for r in field] == sorted(r.rank for r in field)
        games = conn.execute(select(fixture).where(fixture.c.stage == NCAA,
                                                   fixture.c.season_id == 1)).all()
        assert len(games) == 47 and all(g.status == "played" for g in games)
        seed_of = {r.club_id: r.seed for r in field}
        first = [g for g in games if g.round == 0]
        assert len(first) == 16
        assert all(seed_of[g.home_club_id] > 16 and seed_of[g.away_club_id] > 16 for g in first)
        second = [g for g in games if g.round == 1]
        assert sorted(min(seed_of[g.home_club_id], seed_of[g.away_club_id]) for g in second) == \
            list(range(1, 17))
        for g in games:
            assert g.date == f"{2026}-{college.rules.ncaa.rounds[g.round]}"
            if g.round < college.rules.ncaa.neutral_from:
                assert not g.neutral and seed_of[g.home_club_id] < seed_of[g.away_club_id]
            else:
                assert g.neutral
            if g.home_goals == g.away_goals:
                assert g.home_pens is not None
        final = [g for g in games if g.round == 5]
        assert len(final) == 1 and final[0].date == "2026-12-14"
        title = conn.execute(select(league_title).where(
            league_title.c.title == "NCAA Championship")).one()
        f = final[0]
        winner = (f.home_club_id if (f.home_goals, f.home_pens or 0) > (f.away_goals,
                                                                         f.away_pens or 0)
                  else f.away_club_id)
        assert title.club_id == winner and title.won_on == "2026-12-14"


def test_the_draft_pool(played: _Season) -> None:
    world = get_world()
    with _conn(played.after_cup) as conn:
        meta = read_meta(conn)
        pool = draft_pool(conn, world, meta, 1)
        seniors = [p for p in pool if p.class_year == "Sr"]
        ga = [p for p in pool if p.ga]
        assert len(seniors) > 800 and 1 <= len(ga) <= 8
        assert all(p.class_year != "Sr" for p in ga)
        assert all(18 <= p.age <= 25 for p in pool)
        assert pool[0].overall + pool[0].potential >= pool[-1].overall + pool[-1].potential
        best = np.percentile([p.overall for p in pool], 99)
        assert 52 <= best <= 64, best
        # Not signable until he turns pro; then he is a free agent like any other.
        pick = pool[0]
        mls = int(conn.execute(text("SELECT id FROM club WHERE source_league = 'MLS' "
                                    "ORDER BY id LIMIT 1")).scalar_one())
        move = Move(pick.player_id, mls, 0, 200_000_00, date(2029, 6, 30))
        with pytest.raises(MoveRefused, match="college"):
            validate_move(conn, world, meta, move, meta.current_date)
        turn_pro(conn, meta, pick.player_id, meta.current_date)
        try:
            validate_move(conn, world, meta, move, meta.current_date)
        except MoveRefused as refused:
            assert "college" not in str(refused)
        assert pick.player_id not in {p.player_id for p in draft_pool(conn, world, meta, 1)}
        assert conn.execute(text("SELECT COUNT(*) FROM contract WHERE person_id = :p AND "
                                 "is_active = 1"), {"p": pick.player_id}).scalar_one() == 0


def test_the_rollover_graduates_and_recruits(played: _Season) -> None:
    world = get_world()
    with _conn(played.path) as conn:
        assert read_meta(conn).season_id == 2
        status = Counter((r.status, r.class_year) for r in conn.execute(text(
            "SELECT status, class_year FROM college_player")))
        assert not any(s == "prospect" for s, _ in status)  # drafted or let go
        assert sum(n for (s, _), n in status.items() if s == "undrafted") > 800
        freshmen = conn.execute(text("SELECT COUNT(*) FROM college_player WHERE status = "
                                     "'enrolled' AND class_year = 1 AND entered_season = 2")
                                ).scalar_one()
        assert freshmen > 1000
        assert status[("enrolled", 1)] == freshmen  # last season's freshmen moved up
        assert not any(c > 4 for s, c in status if s == "enrolled")
        rosters = [r[0] for r in conn.execute(text(
            "SELECT COUNT(*) FROM college_player WHERE status = 'enrolled' GROUP BY club_id"))]
        assert min(rosters) >= 20 and max(rosters) <= 34
        # The undrafted have no college contract; the enrolled all do, at their program.
        assert conn.execute(text(
            "SELECT COUNT(*) FROM college_player cp JOIN contract k ON k.person_id = "
            "cp.player_id AND k.is_active = 1 AND k.kind = 'college' "
            "WHERE cp.status != 'enrolled'")).scalar_one() == 0
        assert conn.execute(text(
            "SELECT COUNT(*) FROM college_player cp WHERE cp.status = 'enrolled' AND NOT EXISTS "
            "(SELECT 1 FROM contract k WHERE k.person_id = cp.player_id AND k.is_active = 1 "
            "AND k.kind = 'college' AND k.club_id = cp.club_id)")).scalar_one() == 0
        comp = college_competition(conn, world)
        assert conn.execute(select(fixture.c.id).where(
            fixture.c.competition_id == comp, fixture.c.season_id == 2)).first() is not None


def test_college_stays_out_of_the_professional_game(played: _Season) -> None:
    assert played.built > 0
    assert played.leaks == []  # no college player was ever among the market's players
    with _conn(played.path) as conn:
        college = "SELECT club_id FROM college_team"
        assert conn.execute(text(f"SELECT COUNT(*) FROM club_finance WHERE club_id IN "
                                 f"({college})")).scalar_one() == 0
        assert conn.execute(text(f"SELECT COUNT(*) FROM finance_ledger WHERE club_id IN "
                                 f"({college})")).scalar_one() == 0
        assert conn.execute(text(f"SELECT COUNT(*) FROM contract WHERE club_id IN ({college}) "
                                 "AND kind != 'college'")).scalar_one() == 0  # no youth intake
        assert conn.execute(text(f"SELECT COUNT(*) FROM transfer WHERE to_club_id IN "
                                 f"({college}) OR from_club_id IN ({college})")
                            ).scalar_one() == 0
        assert conn.execute(text(f"SELECT COUNT(*) FROM club_league_membership WHERE club_id "
                                 f"IN ({college})")).scalar_one() == 0
        reputations = {r[0] for r in conn.execute(text(
            f"SELECT reputation FROM club WHERE id IN ({college})"))}
        assert reputations <= set(get_world().defs.college.rules.roster.reputation_by_tier
                                  .values())  # no drift
