"""W6 E3 on the real world: a watch-only career with the European competitions on, through
the league phases (to the end of January). Every competition's 36 clubs play their 8 (or 6)
matches on the calendar's matchdays, two (or one) from each pot, never a club of their own
country nor more than two of one; the table is final, with positions 1-36, and the money is
paid. Needs the built world."""

import shutil
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date
from typing import Any

import pytest
from sqlalchemy import Engine, select, text

from footsim.api.europe import europe, summaries
from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.persistence.schema import competition, continental_entry, finance_ledger, fixture
from footsim.world import career
from footsim.world.context import World, get_world
from footsim.world.cups import REST_DAYS
from footsim.world.europe.common import europe_calendar
from footsim.world.meta import read_meta

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
END = date(2027, 2, 1)


@pytest.fixture(scope="module")
def season(tmp_path_factory: pytest.TempPathFactory) -> tuple[Engine, World]:
    base = get_world()
    world = replace(base, defs=replace(base.defs, europe=base.defs.europe.model_copy(
        update={"enabled": True})))
    path = tmp_path_factory.mktemp("europe-lp") / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        career.initialize_career(conn, world, None, None, seed=13)
    with engine.begin() as conn:
        while read_meta(conn).current_date < END:
            career.advance(conn, world, max_days=(END - read_meta(conn).current_date).days)
    return engine, world


def _phase(engine: Engine, key: str) -> tuple[list[Any], list[Any]]:
    with engine.connect() as conn:
        comp_id = conn.execute(select(competition.c.id).where(competition.c.key == key)
                               ).scalar_one()
        entries = conn.execute(select(continental_entry).where(
            continental_entry.c.season_id == 1,
            continental_entry.c.competition_id == comp_id)).all()
        games = conn.execute(select(fixture).where(
            fixture.c.season_id == 1, fixture.c.stage == key,
            fixture.c.round.between(1, 8))).all()
    return list(entries), list(games)


@pytest.mark.parametrize("key", ["UCL", "UEL", "UECL"])
def test_the_league_phase_is_drawn_and_played(season: tuple[Engine, World], key: str) -> None:
    engine, world = season
    comp = world.defs.continental[key]
    phase = comp.league_phase
    entries, games = _phase(engine, key)
    assert len(entries) == phase.clubs
    assert all(g.status == "played" for g in games)
    assert len(games) == phase.clubs * phase.matches // 2
    pot = {e.club_id: e.pot for e in entries}
    assert Counter(pot.values()) == {p: phase.pot_size for p in range(1, phase.pots + 1)}
    with engine.connect() as conn:
        nation = dict(conn.execute(text(
            "SELECT c.id, n.code FROM club c JOIN nation n ON n.id = c.nation_id")).all())
    dates = europe_calendar(world, 1).competitions[key].league_phase
    met: dict[int, list[int]] = defaultdict(list)
    homes: Counter[int] = Counter()
    for g in games:
        assert g.date in {d.isoformat() for d in dates[g.round - 1]}, (key, g.round, g.date)
        met[g.home_club_id].append(g.away_club_id)
        met[g.away_club_id].append(g.home_club_id)
        homes[g.home_club_id] += 1
    for club_id, opponents in met.items():
        assert len(set(opponents)) == len(opponents) == phase.matches
        assert Counter(pot[o] for o in opponents) == {p: phase.per_pot
                                                      for p in range(1, phase.pots + 1)}
        assert homes[club_id] == phase.matches // 2
        countries = Counter(nation[o] for o in opponents)
        assert nation[club_id] not in countries
        assert max(countries.values()) <= 3  # 2 unless the draw had to relax it


@pytest.mark.parametrize("key", ["UCL", "UEL", "UECL"])
def test_the_table_is_final_and_the_money_paid(season: tuple[Engine, World], key: str) -> None:
    engine, world = season
    entries, games = _phase(engine, key)
    assert sorted(e.position for e in entries) == list(range(1, 37))
    prize = world.defs.finance.europe_prizes[key]
    with engine.connect() as conn:
        comp_id = conn.execute(select(competition.c.id).where(competition.c.key == key)
                               ).scalar_one()
        paid = dict(conn.execute(select(finance_ledger.c.club_id,
                                        text("sum(amount_cents)")).where(
            finance_ledger.c.ref_id == comp_id, finance_ledger.c.kind == "prize",
            finance_ledger.c.season_id == 1).group_by(finance_ledger.c.club_id)).all())
    for e in entries:
        won = sum(1 for g in games if (g.home_club_id == e.club_id and g.home_goals > g.away_goals)
                  or (g.away_club_id == e.club_id and g.away_goals > g.home_goals))
        drawn = sum(1 for g in games if e.club_id in (g.home_club_id, g.away_club_id)
                    and g.home_goals == g.away_goals)
        expected = round(prize.participation * 100) + round(
            (won * prize.win + drawn * prize.draw) * 100)
        first, last = world.defs.continental[key].league_phase.to_playoff
        if first <= e.position <= last:  # the knockout play-off is drawn by 1 February
            expected += round(prize.rounds[0] * 100)
        assert paid[e.club_id] == expected, (key, e.club_id)


def test_european_matches_have_room_around_them(season: tuple[Engine, World]) -> None:
    """No club plays within REST_DAYS clear days either side of a European match: its league
    matches and domestic cup ties move out of the way (European dates never do)."""
    engine, world = season
    with engine.connect() as conn:
        rows = conn.execute(select(fixture.c.date, fixture.c.stage, fixture.c.home_club_id,
                                   fixture.c.away_club_id).where(fixture.c.season_id == 1)).all()
    days: dict[int, list[tuple[date, bool]]] = defaultdict(list)
    for r in rows:
        european = r.stage in world.defs.continental
        for c in (r.home_club_id, r.away_club_id):
            days[c].append((date.fromisoformat(r.date), european))
    clashes = []
    for club_id, games in days.items():
        games.sort()
        for (d1, e1), (d2, e2) in zip(games, games[1:], strict=False):
            if (e1 or e2) and (d2 - d1).days <= REST_DAYS:
                clashes.append((club_id, d1.isoformat(), d2.isoformat()))
    assert not clashes, clashes[:10]


def test_the_europe_pages(season: tuple[Engine, World]) -> None:
    """What the Europe page shows (api/europe.py): the qualifying round, the final league
    table in its zones, the matchdays, the knockout play-off drawn, and where each club came
    from in words."""
    engine, world = season
    with engine.connect() as conn:
        ucl = europe(conn, world, "UCL")
        listing = summaries(conn, world)
    assert listing.enabled and [c.key for c in listing.competitions] == ["UCL", "UEL", "UECL"]
    assert listing.competitions[0].stage == "Knockout play-off"
    assert ucl.qualifying.drawn and len(ucl.qualifying.ties) == 4
    assert all(len(t.fixtures) == 2 and t.winner for t in ucl.qualifying.ties)
    phase = ucl.league_phase
    assert phase.final and len(phase.table) == 36
    assert Counter(r.zone for r in phase.table) == {"round_of_16": 8, "playoff": 16, "out": 12}
    assert [len(md.fixtures) for md in phase.matchdays] == [18] * 8
    assert all(f.stage_name == f"League phase, matchday {md.round}"
               for md in phase.matchdays for f in md.fixtures)
    assert ucl.knockout[0].drawn and len(ucl.knockout[0].ties) == 8
    assert not ucl.knockout[1].drawn and ucl.winner is None
    assert len(ucl.entries) == 36 and all(e.how for e in ucl.entries)
    assert any(e.how.endswith("in the Premier League") for e in ucl.entries)
