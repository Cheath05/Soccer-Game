"""NCAA Divisions II and III and the transfer portal (W9e) on the base world: the programs and
rosters, the season's fixtures, conference titles and the national tournament, the portal's
entrants as recruits of D-I's class, a signed portal player moving up at the rollover, and the
rollover's seniors leaving and unsigned high-school seniors arriving. Results are written
directly (the match engines aren't what's tested). Needs the built world."""

import itertools
import shutil
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import Connection, Engine, text

from footsim.core.paths import data_dir
from footsim.defs.college import on
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.world.career import initialize_career
from footsim.world.college import lower
from footsim.world.college.recruiting import GONE, SIGNED, enroll_class
from footsim.world.college.season import _season_start
from footsim.world.context import World, get_world
from footsim.world.meta import read_meta

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


@pytest.fixture(scope="module")
def career(tmp_path_factory: pytest.TempPathFactory) -> tuple[Engine, World]:
    path: Path = tmp_path_factory.mktemp("lower") / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    world = get_world()
    with engine.begin() as conn:
        initialize_career(conn, world, None, "Coach", seed=5,
                          college_program="UMBC Retrievers")
    return engine, world


def _play(conn: Connection, comp: int, stage: str, before: date, seed: int) -> None:
    """Results for the competition's scheduled ``stage`` fixtures before ``before``."""
    rng = np.random.default_rng(seed)
    rows = conn.execute(text(
        "SELECT id FROM fixture WHERE competition_id = :c AND stage = :s AND "
        "status = 'scheduled' AND date < :d"),
        {"c": comp, "s": stage, "d": before.isoformat()}).all()
    if not rows:
        return
    conn.execute(text("UPDATE fixture SET status = 'played', home_goals = :h, away_goals = :a, "
                      "home_pens = :hp, away_pens = :ap WHERE id = :f"),
                 [{"f": r.id, "h": int(h), "a": int(a),
                   "hp": 5 if h == a and stage != "lower" else None,
                   "ap": 4 if h == a and stage != "lower" else None}
                  for r, h, a in zip(rows, rng.poisson(1.4, len(rows)),
                                     rng.poisson(1.2, len(rows)), strict=True)])


def test_the_programs_and_their_fixtures(career: tuple[Engine, World]) -> None:
    engine, world = career
    defs = lower.rules(world)
    assert defs is not None
    with engine.connect() as conn:
        teams = dict(conn.execute(text(
            "SELECT division, COUNT(*) FROM lower_team GROUP BY division")).all())
        assert teams == {d: sum(len(c.teams) for c in div.conferences.values())
                         for d, div in defs.divisions.items()}
        sizes = {int(n) for (n,) in conn.execute(text(
            "SELECT COUNT(*) FROM lower_player GROUP BY club_id"))}
        assert sizes == {defs.roster_size}
        # Their players are college players: the professional game leaves them out.
        assert conn.execute(text(
            "SELECT COUNT(*) FROM lower_player WHERE player_id NOT IN "
            "(SELECT player_id FROM (SELECT player_id FROM college_player WHERE status IN "
            "('enrolled','prospect') UNION SELECT player_id FROM lower_player))")).scalar() == 0
        comps = lower.competitions(conn, world)
        assert set(comps) == {2, 3}
        for div, comp in comps.items():
            played = conn.execute(text(
                "SELECT home_club_id AS c FROM fixture WHERE competition_id = :c UNION ALL "
                "SELECT away_club_id FROM fixture WHERE competition_id = :c"),
                {"c": comp}).all()
            counts: dict[int, int] = {}
            for (c,) in played:
                counts[int(c)] = counts.get(int(c), 0) + 1
            assert len(counts) == teams[div]
            assert max(counts.values()) <= defs.regular_season.matches


def test_the_season_and_the_portal(career: tuple[Engine, World]) -> None:
    engine, world = career
    defs = lower.rules(world)
    assert defs is not None
    with engine.begin() as conn:
        meta = read_meta(conn)
        start = _season_start(conn, meta.season_id)
        comps = lower.competitions(conn, world)
        for div, comp in comps.items():
            _play(conn, comp, "lower", date(start.year, 12, 31), div)
        selection = date(start.year, 11, 9)
        lower.progress_lower(conn, world, meta, selection)
        for div in comps:
            seeds = lower.entries(conn, meta.season_id, lower.event(div))
            assert len(seeds) == defs.divisions[div].tournament.teams
            autos = conn.execute(text(
                "SELECT COUNT(*) FROM college_entry WHERE event = :e AND bid = 'auto'"),
                {"e": lower.event(div)}).scalar()
            assert autos == sum(c.auto_bid for c in defs.divisions[div].conferences.values())
        # The rounds, day by day, to the champions.
        day = selection
        news: list[str] = []
        while day <= date(start.year, 12, 10):
            for div, comp in comps.items():
                _play(conn, comp, lower.event(div), day + timedelta(days=1), 10 + div)
            news += lower.progress_lower(conn, world, meta, day)
            day += timedelta(days=1)
        assert sum("national champions" in n for n in news) == 2
        assert any(n.startswith("The transfer portal opens") for n in news)
        portal = conn.execute(text(
            "SELECT r.*, lp.class_year FROM recruit r JOIN lower_player lp ON "
            "lp.player_id = r.player_id WHERE r.source = 'portal' AND r.class_season = :c"),
            {"c": meta.season_id + 1}).all()
        assert 0 < len(portal) <= defs.portal.entrants
        assert all(r.class_year < 4 and r.overall >= defs.portal.min_overall
                   and r.status == "open" for r in portal)
        # Signed with the user, the best one moves up at the rollover, a class on.
        best = max(portal, key=lambda r: r.grade)
        conn.execute(text("UPDATE recruit SET status = :s, club_id = :c, share = 0.5 "
                          "WHERE id = :r"),
                     {"s": SIGNED, "c": meta.user_club_id, "r": best.id})
        rollover = date(start.year + 1, 7, 1)
        enroll_class(conn, world, meta, meta.season_id + 1, rollover)
        moved = conn.execute(text(
            "SELECT club_id, class_year, scholarship FROM college_player WHERE player_id = :p"),
            {"p": best.player_id}).one()
        assert (moved.club_id, moved.class_year, moved.scholarship) == (
            meta.user_club_id, min(4, best.class_year + 1), 0.5)
        assert conn.execute(text("SELECT COUNT(*) FROM lower_player WHERE player_id = :p"),
                            {"p": best.player_id}).scalar() == 0
        assert conn.execute(text(
            "SELECT club_id FROM contract WHERE person_id = :p AND is_active = 1"),
            {"p": best.player_id}).scalar() == meta.user_club_id
        # The rollover: seniors leave, the unsigned high-school seniors arrive.
        seniors = conn.execute(text("SELECT COUNT(*) FROM lower_player WHERE class_year >= 4")
                               ).scalar_one()
        unsigned = conn.execute(text(
            "SELECT COUNT(*) FROM recruit WHERE class_season = :c AND status = :g AND "
            "player_id IS NULL AND source IS NULL"),
            {"c": meta.season_id + 1, "g": GONE}).scalar_one()
        assert seniors > 0 and unsigned > 0
        lower.lower_turnover(conn, world, meta, meta.season_id + 1, rollover)
        assert conn.execute(text("SELECT COUNT(*) FROM lower_player WHERE class_year > 4")
                            ).scalar() == 0
        placed = conn.execute(text(
            "SELECT COUNT(*) FROM recruit r JOIN lower_player lp ON lp.player_id = r.player_id "
            "WHERE r.status = :s AND lp.class_year = 1"),
            {"s": lower.LOWER_JOINED}).scalar_one()
        assert placed == min(unsigned, placed) and placed > 0
        sizes = {int(n) for (n,) in conn.execute(text(
            "SELECT COUNT(*) FROM lower_player GROUP BY club_id"))}
        assert sizes == {defs.roster_size}
        conn.rollback()


def test_rankings_are_the_rpi(career: tuple[Engine, World]) -> None:
    """D-II and D-III are ranked by the RPI, as D-I (22 Nov)."""
    engine, world = career
    with engine.begin() as conn:
        meta = read_meta(conn)
        start = _season_start(conn, meta.season_id)
        comps = lower.competitions(conn, world)
        _play(conn, comps[2], "lower", date(start.year, 10, 1), 7)
        ratings = lower.rpi_ratings(conn, world, 2, meta.season_id)
        order = lower.ranking(conn, world, 2, meta.season_id)
        assert order and set(order) == set(ratings)
        assert all(ratings[a] >= ratings[b] for a, b in itertools.pairwise(order))
        conn.rollback()


def test_the_all_division_tournament(career: tuple[Engine, World]) -> None:
    """The All-Division Tournament (22 Nov): once the three national finals are played, each
    division's champion and best by the RPI, the best entering latest; each round drawn
    across the divisions; a champion, and the news."""
    from footsim.world.college import all_division
    from footsim.world.college.season import NATIONAL_TITLE, _title, college_competition

    engine, world = career
    adt = all_division.rules(world)
    assert adt is not None
    with engine.begin() as conn:
        meta = read_meta(conn)
        start = _season_start(conn, meta.season_id)
        comps = lower.competitions(conn, world)
        for div, comp in comps.items():
            _play(conn, comp, "lower", date(start.year, 12, 31), div)
        d1 = college_competition(conn, world)
        assert d1 is not None
        _play(conn, d1, "college", date(start.year, 12, 31), 1)
        news: list[str] = []
        day = date(start.year, 11, 9)
        while day <= date(start.year, 12, 10):
            for div, comp in comps.items():
                _play(conn, comp, lower.event(div), day + timedelta(days=1), 10 + div)
            news += lower.progress_lower(conn, world, meta, day)
            day += timedelta(days=1)
        # No field until D-I has its champion too.
        assert all_division.progress_all_division(conn, world, meta, date(start.year, 12, 16)
                                                  ) == []
        assert all_division.field(conn, world, meta.season_id) == []
        champion = int(conn.execute(text(
            "SELECT club_id FROM college_team ORDER BY club_id DESC LIMIT 1")).scalar_one())
        _title(conn, d1, meta.season_id, NATIONAL_TITLE, champion, "champion", "NCAA",
               date(start.year, 12, 14))
        assert all_division.progress_all_division(conn, world, meta, date(start.year, 12, 14)
                                                  ) == []  # before selection day
        day = on(adt.selection, start)
        comp: int | None = None
        while day <= date(start.year + 1, 1, 10):
            news += all_division.progress_all_division(conn, world, meta, day)
            comp = all_division.competition_id(conn, world)
            if comp is not None:
                _play(conn, comp, all_division.ALL_DIVISION, day + timedelta(days=1), 99)
            day += timedelta(days=1)
        teams, matches = all_division.matches(conn, world, meta.season_id)
        assert len(teams) == sum(adt.field_size(d) for d in adt.entries)
        assert [e.seed for e in teams] == list(range(1, len(teams) + 1))
        mine = next(e for e in teams if e.club_id == champion)
        assert (mine.division, mine.rank, mine.enters) == (1, 1, len(adt.entries[1]) - 1)
        # Each division's champion is its first, and the best enter latest.
        for d in adt.entries:
            ours = sorted((e for e in teams if e.division == d), key=lambda e: e.rank)
            assert [e.rank for e in ours] == list(range(1, adt.field_size(d) + 1))
            assert all(a.enters >= b.enters for a, b in itertools.pairwise(ours))
        assert all(a.enters >= b.enters for a, b in itertools.pairwise(teams))
        # Within a round's entrants, the divisions take turns, D-I first.
        later = {d: [sum(c[k + 1:]) for k in range(len(c))] for d, c in adt.entries.items()}
        for k in range(len(adt.rounds)):
            group = [e for e in teams if e.enters == k]
            places = [(e.rank - later[e.division][k], e.division) for e in group]
            assert places == sorted(places)
        # Every match of the set bracket played, at a neutral ground from neutral_from, the
        # better seed at home before it.
        assert [len([m for m in matches if m.round == k]) for k in range(len(adt.rounds))] == [
            len(games) for games in adt.bracket]
        for m in matches:
            assert m.a is not None and m.b is not None and m.winner in (m.a, m.b)
            assert m.fixture is not None
            assert bool(m.fixture.neutral) == (m.round >= adt.neutral_from)
            if not m.fixture.neutral:
                assert int(m.fixture.home_club_id) == min((m.a, m.b), key=lambda e: e.seed).club_id
            # The sides are the bracket's: an entrant, or the named match's winner.
            for code, team in zip(adt.bracket[m.round][m.index], (m.a, m.b), strict=True):
                entrant, winner = adt.entrant(code), adt.winner(code)
                if entrant is not None:
                    assert (team.division, team.rank) == entrant
                else:
                    assert winner is not None
                    assert team == next(x.winner for x in matches
                                        if (x.round, x.index) == winner)
        # Mixed across the divisions, but D-II and D-III's top two meet none of D-I's top four
        # before the quarterfinals.
        assert any(m.a.division != m.b.division for m in matches if m.round == 0 and m.a and m.b)
        quarters = adt.round_names.index("Quarterfinals")
        for m in matches:
            if m.round < quarters and m.a is not None and m.b is not None:
                tops = sorted((t for t in (m.a, m.b) if t.rank <= (4 if t.division == 1 else 2)),
                              key=lambda t: t.division)
                assert not (len(tops) == 2 and tops[0].division == 1 and tops[1].division > 1)
        won = conn.execute(text(
            "SELECT club_id FROM league_title WHERE competition_id = :c AND title = :t"),
            {"c": comp, "t": all_division.TITLE}).scalar_one()
        final = next(m for m in matches if m.round == len(adt.rounds) - 1)
        assert final.winner is not None and won == final.winner.club_id
        assert any("field of" in n for n in news)
        assert sum("All-Division champions" in n for n in news) == 1
        # The champion's season says so.
        assert all_division.run(conn, world, meta.season_id, won) == "All-Division champions"
        conn.rollback()


def test_the_set_bracket_rejects_a_broken_one() -> None:
    """The bracket's checks: every entrant once, every winner but the final's on once."""
    from typing import Any

    from pydantic import ValidationError

    from footsim.defs.college import AllDivisionDef

    base: dict[str, Any] = {"key": "X", "name": "X", "short_name": "X", "selection": "12-15",
            "rounds": ["12-16", "12-18"], "round_names": ["Semifinals", "Final"],
            "neutral_from": 1}
    good = AllDivisionDef(**base, bracket=[[("D1-1", "D2-2"), ("D2-1", "D1-2")],
                                           [("R1M1", "R1M2")]])
    assert good.entries == {1: [2], 2: [2]} and good.entry_round(2, 1) == 0
    for broken in ([[("D1-1", "D2-2"), ("D2-1", "D1-1")], [("R1M1", "R1M2")]],  # twice
                   [[("D1-1", "D2-2"), ("D2-1", "D1-2")], [("R1M1", "R1M1")]],  # a winner twice
                   [[("D1-1", "D2-2"), ("D2-1", "D1-3")], [("R1M1", "R1M2")]],  # no D-I 2nd
                   [[("D1-1", "D2-2"), ("D2-1", "D1-2")], [("R1M1", "R2M1")]]):  # not earlier
        with pytest.raises(ValidationError):
            AllDivisionDef(**base, bracket=broken)
