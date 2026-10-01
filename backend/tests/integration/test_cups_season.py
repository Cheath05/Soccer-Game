"""A whole season with the cups (P17), watched without a club of one's own: both cups reach a
final and a winner, every round has the clubs it should, and no club ever plays twice within
two days of a cup match moving its league match. Skipped when the base world hasn't been
built (it needs the locally downloaded EA FC 27 file, which isn't in the repository)."""

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


def test_a_season_of_cups(tmp_path: Path) -> None:
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
        for key in ("FA_CUP", "EFL_CUP"):
            cup = world.defs.cups[key]
            ties = conn.execute(select(cup_tie).where(
                cup_tie.c.season_id == 1, cup_tie.c.competition_id == ids[key])).all()
            for index, (clubs, through) in enumerate(cup.sizes(sizes)):
                in_round = [t for t in ties if t.round == index]
                entered = {c for t in in_round for c in (t.club_a_id, t.club_b_id) if c}
                assert len(entered) == clubs, (key, index)
                assert len({t.winner_club_id for t in in_round}) == through, (key, index)
            assert any(t.round == len(cup.rounds) - 1 and t.winner_club_id for t in ties)
        # Every match, league, play-off and cup, at least two clear days after a club's last,
        # and every league match (moved or not) within its league's dates.
        calendar = world.defs.calendars["ENG-2026-27"]
        keys = {cid: key for key, cid in ids.items()}
        days: dict[int, list[date]] = defaultdict(list)
        for f in conn.execute(select(fixture).where(fixture.c.season_id == 1)):
            assert f.status == "played"
            if f.stage == "league":
                dates = calendar.competitions[keys[f.competition_id]]
                assert dates.start <= date.fromisoformat(f.date) <= dates.end
            for club in (f.home_club_id, f.away_club_id):
                days[club].append(date.fromisoformat(f.date))
        tight = [(club, a, b) for club, ds in days.items() for a, b in zip(
            sorted(ds), sorted(ds)[1:], strict=False) if (b - a).days < 3]
        assert not tight, tight[:5]
        # The next season starts with its Carabao Cup first round drawn.
        assert conn.execute(text("SELECT COUNT(*) FROM cup_tie WHERE season_id = 2")
                            ).scalar_one() > 0
    engine.dispose()


def test_a_save_from_before_the_cups_starts_them_if_their_first_round_is_ahead(
        tmp_path: Path) -> None:
    """The user's Chelsea career was saved on 1 Jul, before cups existed: its new season still
    gets them, its league matches moved around the ties."""
    from footsim.world.meta import read_meta
    from footsim.world.season import after_day

    world = get_world()
    path = tmp_path / "old.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, world, None, None, seed=6)
        conn.execute(text("DELETE FROM fixture WHERE stage IN ('FA_CUP', 'EFL_CUP')"))
        conn.execute(text("DELETE FROM cup_tie"))  # as a save from before the cups
        meta = read_meta(conn)
        messages = after_day(conn, world, meta, meta.current_date)
        drawn = conn.execute(text("SELECT COUNT(*) FROM cup_tie WHERE round = 0")).scalar_one()
        assert drawn == 36 + 16 + 16  # the Carabao Cup's 36 ties, the FA Cup's 16 and 16 byes
        assert after_day(conn, world, meta, meta.current_date) == messages == []  # once only
    engine.dispose()
