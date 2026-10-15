"""W7 A3/A4: who plays in Europe (world/europe/places.py, UEFA's access list by ranking position)
and the qualifying rounds (world/europe/qualifying.py). The rules on made-up tables, then a
watch-only career on the real world through August (that part needs the built world)."""

import shutil
from collections import Counter
from dataclasses import replace
from datetime import date
from typing import Any

import pytest
from sqlalchemy import Engine, select, text

from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.persistence.schema import competition, continental_entry, cup_tie, fixture
from footsim.world import career
from footsim.world.context import World, get_world
from footsim.world.europe import places
from footsim.world.europe.places import Entry, qualify
from footsim.world.meta import CareerMeta, read_meta

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
# Season 1 (2026-27): the 2025 ranking applies, and England and Spain have the Performance Spots.
META = CareerMeta(world_seed=3, current_date=date(2026, 7, 1), season_id=1,
                  base_calendar="ENG-2026-27", user_club_id=None, manager_name=None)


def europe_on(world: World) -> World:
    return replace(world, defs=replace(world.defs, europe=world.defs.europe.model_copy(
        update={"enabled": True})))


# --- the rules, on made-up tables -------------------------------------------------------------

def club(code: str, rank: int) -> int:
    """The made-up club finishing ``rank`` in country ``code``."""
    return 1000 * (sorted(get_world().defs.nations).index(code) + 1) + rank


def _fake(monkeypatch: pytest.MonkeyPatch, cups: dict[str, int] | None = None,
          holders: dict[str, int] | None = None, leagues: dict[int, str] | None = None) -> None:
    """Every country 30 clubs in a table (Liechtenstein none: it has no league); cup winners
    and holders as given; a holder's league country as given."""
    def order(_conn: Any, _world: Any, _meta: Any, _season: int, code: str) -> list[int]:
        return [] if code == "LIE" else [club(code, rank) for rank in range(1, 31)]

    monkeypatch.setattr(places, "nation_order", order)
    monkeypatch.setattr(places, "cup_winner", lambda _c, _w, _s, key: (cups or {}).get(key))
    monkeypatch.setattr(places, "holder", lambda _c, _w, _s, key: (holders or {}).get(key))
    monkeypatch.setattr(places, "_league_nation",
                        lambda _c, club_id, _s: (leagues or {}).get(club_id))


def _qualify() -> tuple[dict[int, Entry], list[places.Vacancy]]:
    entries, vacancies = qualify(None, get_world(), META, 1)  # type: ignore[arg-type]
    return {e.club_id: e for e in entries}, vacancies


def test_every_place_is_taken_once(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch)
    placed, vacancies = _qualify()
    count = Counter((e.competition, e.round, e.path) for e in placed.values())
    assert count[("UCL", "LP", None)] == 16 + 3 + 2 + 4 + 2  # positions 1-10, and the EPS
    assert count[("UCL", "PO", "champions")] == 4
    assert count[("UCL", "Q1", "champions")] == 30  # positions 24-54, Liechtenstein aside
    assert count[("UEL", "Q1", "main")] == 16
    assert count[("UECL", "Q1", "main")] == 11 + 21 + 20
    # England: its top four and its Performance Spot (5th) in the Champions League; no cup
    # winners on record, so the FA Cup's place goes to its best club not yet in (6th), its 5th
    # place to the next (7th), and the EFL Cup's (its 6th place) to 8th.
    assert [placed[club("ENG", r)].competition for r in range(1, 9)] == [
        "UCL"] * 5 + ["UEL", "UEL", "UECL"]
    assert placed[club("ENG", 5)].route == "eps:ENG:5"
    assert placed[club("ESP", 5)].route == "eps:ESP:5"
    # No holders yet: their places are left to qualifying.py to fill, from the paths named.
    assert sorted((v.competition, v.round, v.fill_from) for v in vacancies
                  if v.round == "LP") == [("UCL", "LP", "champions"), ("UCL", "LP", "league"),
                                          ("UEL", "LP", "main")]


def test_a_cup_winner_from_lower_down_takes_its_place(monkeypatch: pytest.MonkeyPatch) -> None:
    outsider = 999_001  # a Championship club, say
    _fake(monkeypatch, cups={"FA_CUP": outsider, "EFL_CUP": club("ENG", 2)})
    placed, _ = _qualify()
    assert (placed[outsider].competition, placed[outsider].round) == ("UEL", "LP")
    assert placed[outsider].route == "cup:FA_CUP"
    # England's 5th place in the Europa League passes to 6th (5th has the Performance Spot);
    # the EFL Cup winners are in the Champions League already, so its place goes to 7th.
    assert placed[club("ENG", 6)].competition == "UEL"
    assert placed[club("ENG", 7)].competition == "UECL"


def test_the_holders(monkeypatch: pytest.MonkeyPatch) -> None:
    ucl_holders = club("ENG", 3)  # in the Champions League through their league anyway
    uel_holders = club("ESP", 9)  # nowhere through their league
    uecl_holders = club("ITA", 6)  # in the Conference League play-off through their league
    _fake(monkeypatch, holders={"UCL": ucl_holders, "UEL": uel_holders, "UECL": uecl_holders},
          leagues={ucl_holders: "ENG", uel_holders: "ESP", uecl_holders: "ITA"})
    placed, vacancies = _qualify()
    assert placed[ucl_holders].route == "league:ENG:3"  # its own place: the holders' is empty
    assert ("UCL", "LP", "champions") in {(v.competition, v.round, v.fill_from)
                                          for v in vacancies}
    assert placed[uel_holders].route == "holder:UEL" and placed[uel_holders].competition == "UCL"
    assert placed[uecl_holders].route == "holder:UECL"
    assert (placed[uecl_holders].competition, placed[uecl_holders].round) == ("UEL", "LP")
    # Italy's cup place goes to its 5th (no winners on record), its 5th place to 7th, and its
    # 6th (the Conference League's play-off) to 8th.
    assert [placed[club("ITA", r)].competition for r in (5, 7, 8)] == ["UEL", "UEL", "UECL"]


# --- a career through August ------------------------------------------------------------------

@pytest.fixture(scope="module")
def august(tmp_path_factory: pytest.TempPathFactory) -> tuple[Engine, World]:
    if not BASE_WORLD.exists():
        pytest.skip("base world not built")
    world = europe_on(get_world())
    path = tmp_path_factory.mktemp("europe") / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        career.initialize_career(conn, world, None, None, seed=7)
    return engine, world


def _entries(engine: Engine) -> list[Any]:
    with engine.connect() as conn:
        return list(conn.execute(
            select(continental_entry, competition.c.key)
            .join(competition, competition.c.id == continental_entry.c.competition_id)
            .where(continental_entry.c.season_id == 1)).all())


def test_a_first_season_starts_with_the_first_rounds(august: tuple[Engine, World]) -> None:
    engine, _ = august
    entries = _entries(engine)
    assert len({e.club_id for e in entries}) == len(entries)
    with engine.connect() as conn:
        # How 2025-26 really finished (europe/season_before.yaml): its top four.
        eng_top4 = {r.id for r in conn.execute(text(
            "SELECT id FROM club WHERE name IN ('Arsenal', 'Manchester City', 'Man Utd', "
            "'Aston Villa')"))}
        first_round = conn.execute(select(fixture.c.date).where(
            fixture.c.season_id == 1, fixture.c.stage == "UCL",
            fixture.c.round == -3)).scalars().all()
    english = {e.club_id for e in entries
               if e.route in {f"league:ENG:{r}" for r in range(1, 5)}}
    assert english == eng_top4
    assert all(e.key == "UCL" and e.stage == "league_phase" for e in entries
               if e.club_id in english)
    assert {e.route.split(":")[1] for e in entries if e.route.startswith("eps:")} == {
        "ENG", "ESP"}
    assert first_round and set(first_round) <= {"2026-07-07", "2026-07-08", "2026-07-14",
                                                "2026-07-15"}


def test_qualifying_sends_winners_up_and_losers_down(august: tuple[Engine, World]) -> None:
    engine, world = august
    with engine.begin() as conn:
        while read_meta(conn).current_date < date(2026, 9, 1):
            career.advance(conn, world, max_days=(date(2026, 9, 1)
                                                  - read_meta(conn).current_date).days)
    entries = _entries(engine)
    assert {e.stage for e in entries} <= {"league_phase", "out"}
    assert Counter(e.key for e in entries if e.stage == "league_phase") == {
        "UCL": 36, "UEL": 36, "UECL": 36}
    with engine.connect() as conn:
        ties = conn.execute(select(cup_tie).join(
            competition, competition.c.id == cup_tie.c.competition_id).where(
            competition.c.type == "continental", cup_tie.c.round <= 0)).all()
    assert ties and all(t.winner_club_id for t in ties)
    # Clubs knocked out of a higher competition's qualifying went on in a lower one.
    dropped = [e for e in entries if e.came_from]
    assert dropped and all(e.came_from.split(":")[0] in ("UCL", "UEL") for e in dropped)
    assert all(e.key != e.came_from.split(":")[0] for e in dropped)


def test_the_same_seed_qualifies_the_same_clubs(tmp_path: Any) -> None:
    if not BASE_WORLD.exists():
        pytest.skip("base world not built")
    world = europe_on(get_world())
    runs = []
    for k in range(2):
        path = tmp_path / f"c{k}.sqlite"
        shutil.copy(BASE_WORLD, path)
        engine = open_database(path)
        migrate(engine)
        with engine.begin() as conn:
            career.initialize_career(conn, world, None, None, seed=11)
        runs.append(sorted((e.key, e.club_id, e.stage, e.route, e.entry_round, e.path)
                           for e in _entries(engine)))
        engine.dispose()
    assert runs[0] == runs[1]
