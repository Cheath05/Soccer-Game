"""A whole season with every league (W2) and every country's cups (P17), watched without a club
of one's own: every league finishes and starts the next season the right size, with clubs
promoted and relegated in every country; every cup reaches a final and a winner, every round has
the clubs it should, and no club ever plays twice within two days of a cup match moving its
league match.
Skipped when the base world hasn't been built (it needs the locally downloaded EA FC 27 file,
which isn't in the repository)."""

import shutil
from collections import defaultdict
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select, text

from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.persistence.schema import competition, cup_tie, fixture
from footsim.world.career import advance, initialize_career
from footsim.world.context import get_world

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


def test_a_season_of_leagues_and_cups(tmp_path: Path) -> None:
    world = get_world()
    path = tmp_path / "season.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, world, None, None, seed=5)
    with engine.begin() as conn:
        result = advance(conn, world, max_days=400)
    assert result.stop == "season_end"
    with engine.connect() as conn:
        ids = {r.key: r.id for r in conn.execute(select(competition.c.id, competition.c.key))}
        sizes = {key: league.clubs for key, league in world.defs.leagues.items()}
        for key, cup in world.defs.cups.items():
            ties = conn.execute(select(cup_tie).where(
                cup_tie.c.season_id == 1, cup_tie.c.competition_id == ids[key])).all()
            for index, (clubs, through) in enumerate(cup.sizes(sizes)):
                in_round = [t for t in ties if t.round == index]
                entered = {c for t in in_round for c in (t.club_a_id, t.club_b_id) if c}
                assert len(entered) == clubs, (key, index)
                assert len({t.winner_club_id for t in in_round}) == through, (key, index)
            # Every country's cup finishes with a winner from that country's league clubs, and
            # its competition row says which country it belongs to.
            winners = [t.winner_club_id for t in ties
                       if t.round == len(cup.rounds) - 1 and t.winner_club_id]
            assert len(winners) == 1, key
            nation = conn.execute(text(
                "SELECT n.code FROM competition c JOIN nation n ON n.id = c.nation_id "
                "WHERE c.key = :k"), {"k": key}).scalar_one()
            assert nation == cup.nation, key
            home = conn.execute(text(
                "SELECT l.key FROM club_league_membership m JOIN competition l "
                "ON l.id = m.competition_id WHERE m.season_id = 1 AND m.club_id = :c"),
                {"c": winners[0]}).scalar_one()
            assert world.defs.leagues[home].nation == cup.nation, key
        assert {c.nation for c in world.defs.cups.values()} == {
            league.nation for league in world.defs.leagues.values()}
        # Every match, league, play-off and cup, at least two clear days after a club's last,
        # and every league match (moved or not) within its league's dates.
        keys = {cid: key for key, cid in ids.items()}
        days: dict[int, list[date]] = defaultdict(list)
        for f in conn.execute(select(fixture).where(fixture.c.season_id == 1)):
            assert f.status == "played"
            if f.stage == "league":
                league = world.defs.leagues[keys[f.competition_id]]
                dates = world.defs.calendars[league.calendar].competitions[league.key]
                assert dates.start <= date.fromisoformat(f.date) <= dates.end
            for club in (f.home_club_id, f.away_club_id):
                days[club].append(date.fromisoformat(f.date))
        tight = [(club, a, b) for club, ds in days.items() for a, b in zip(
            sorted(ds), sorted(ds)[1:], strict=False) if (b - a).days < 3]
        assert not tight, tight[:5]
        # Every league played its season and starts the next one at its size, and clubs went
        # up and down in every country with more than one league.
        for key, league in world.defs.leagues.items():
            finished = conn.execute(text(
                "SELECT COUNT(*) FROM league_final WHERE season_id = 1 AND competition_id = :c"),
                {"c": ids[key]}).scalar_one()
            assert finished == league.clubs, key
            nxt = conn.execute(text(
                "SELECT COUNT(*) FROM club_league_membership WHERE season_id = 2 AND "
                "competition_id = :c"), {"c": ids[key]}).scalar_one()
            assert nxt == league.clubs, key
        moved = conn.execute(text("""
            SELECT k.key FROM club_league_membership a
            JOIN club_league_membership b ON b.club_id = a.club_id AND b.season_id = 2
            JOIN competition k ON k.id = a.competition_id
            WHERE a.season_id = 1 AND a.competition_id != b.competition_id""")).scalars().all()
        assert {"ENG1", "ESP1", "ITA1", "GER1", "FRA1", "GER3"} <= set(moved)
        # The next season starts with every cup's first round drawn.
        for key, cup in world.defs.cups.items():
            first = conn.execute(text(
                "SELECT COUNT(*) FROM cup_tie WHERE season_id = 2 AND round = 0 "
                "AND competition_id = :c"), {"c": ids[key]}).scalar_one()
            assert first == cup.sizes(sizes)[0][1], key
    engine.dispose()


def test_a_save_from_before_the_cups_starts_them_if_their_first_round_is_ahead(
        tmp_path: Path) -> None:
    """The user's Chelsea career was saved on 1 Jul, before cups existed: its new season still
    gets them (every country's, as each one's first round is still ahead), its league matches
    moved around the ties."""
    from footsim.world.meta import read_meta
    from footsim.world.season import after_day

    world = get_world()
    path = tmp_path / "old.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, world, None, None, seed=6)
        stages = ", ".join(f"'{key}'" for key in world.defs.cups)
        conn.execute(text(f"DELETE FROM fixture WHERE stage IN ({stages})"))
        conn.execute(text("DELETE FROM cup_tie"))  # as a save from before the cups
        meta = read_meta(conn)
        messages = after_day(conn, world, meta, meta.current_date)
        drawn = conn.execute(text("SELECT COUNT(*) FROM cup_tie WHERE round = 0")).scalar_one()
        # Each cup's first round has a row for every club that goes through it (a tie to be
        # won, or a bye): the Carabao Cup's 36 ties, the FA Cup's 16 and 16 byes, and so on.
        sizes = {key: league.clubs for key, league in world.defs.leagues.items()}
        assert drawn == sum(cup.sizes(sizes)[0][1] for cup in world.defs.cups.values())
        assert conn.execute(text(f"SELECT COUNT(*) FROM fixture WHERE stage IN ({stages})")
                            ).scalar_one() > 0
        # The day's only news is the AI transfer market's (its window is open): starting the
        # cups makes none, and running the day again adds nothing.
        assert all(" joins " in m for m in messages)
        assert after_day(conn, world, meta, meta.current_date) == []  # once only
    engine.dispose()
