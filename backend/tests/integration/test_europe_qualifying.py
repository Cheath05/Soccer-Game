"""W6 E2: who plays in Europe (world/europe/access.py) and the summer play-off round
(world/europe/stages.py). The rules on made-up tables, then a watch-only career on the real
world through August (that part needs the built world)."""

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
from footsim.world.europe import access
from footsim.world.europe.access import Entry, qualify
from footsim.world.meta import CareerMeta, read_meta

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
META = CareerMeta(world_seed=3, current_date=date(2027, 7, 1), season_id=2,
                  base_calendar="ENG-2026-27", user_club_id=None, manager_name=None)
# Countries in the made-up world with few clubs, as in the real one.
SMALL = {"GRE": 4, "CZE": 3, "UKR": 2, "CYP": 2, "CRO": 2, "HUN": 1, "BUL": 1, "AZE": 1}


def europe_on(world: World) -> World:
    return replace(world, defs=replace(world.defs, europe=world.defs.europe.model_copy(
        update={"enabled": True})))


# --- the rules, on made-up tables ------------------------------------------------------------

def club(code: str, rank: int) -> int:
    """The made-up club finishing ``rank`` in country ``code``."""
    return 1000 * (sorted(get_world().defs.nations).index(code) + 1) + rank


def _fake(monkeypatch: pytest.MonkeyPatch, cups: dict[str, int] | None = None,
          holders: dict[str, int] | None = None) -> None:
    def order(_conn: Any, _world: Any, _meta: Any, _season: int, code: str) -> list[int]:
        return [club(code, rank) for rank in range(1, SMALL.get(code, 30) + 1)]

    monkeypatch.setattr(access, "nation_order", order)
    monkeypatch.setattr(access, "cup_winner", lambda _c, _w, _s, key: (cups or {}).get(key))
    monkeypatch.setattr(access, "holder", lambda _c, _w, _s, key: (holders or {}).get(key))


def _qualify() -> dict[int, Entry]:
    return {e.club_id: e for e in qualify(None, get_world(), META, 2)}  # type: ignore[arg-type]


def test_every_competition_fills_and_each_club_has_one_place(
        monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch)
    placed = _qualify()
    count = Counter((e.competition, e.stage) for e in placed.values())
    assert count == {("UCL", "league_phase"): 32, ("UCL", "qualifying"): 8,
                     ("UEL", "league_phase"): 26, ("UEL", "qualifying"): 12,
                     ("UECL", "league_phase"): 23, ("UECL", "qualifying"): 14}
    # No holders yet: their two UCL places go to the fill countries in turn, the UEL's to the
    # first again.
    fills = Counter((e.competition, e.route) for e in placed.values()
                    if e.route.startswith("fill:"))
    assert fills == {("UCL", "fill:ENG"): 1, ("UCL", "fill:ITA"): 1, ("UEL", "fill:ENG"): 1}
    assert placed[club("ENG", 5)].competition == "UCL"  # England's fill place: its 5th
    assert all(placed[club("ENG", r)].competition == "UCL" for r in range(1, 5))
    assert placed[club("AZE", 1)].competition == "UECL"


def test_places_pass_down_the_table(monkeypatch: pytest.MonkeyPatch) -> None:
    # The Champions League won by England's third, the FA Cup by its runners-up.
    _fake(monkeypatch, cups={"FA_CUP": club("ENG", 2)}, holders={"UCL": club("ENG", 3)})
    placed = _qualify()
    assert placed[club("ENG", 3)].route == "holder:UCL"
    # Third's league place passes to fifth, and England's turn at the fill to sixth.
    ucl = [r for r in range(1, 15) if club("ENG", r) in placed
           and placed[club("ENG", r)].competition == "UCL"]
    assert ucl == [1, 2, 3, 4, 5, 6]
    # The UEL's 5th place goes down to 7th, the FA Cup's (its winner is in the UCL) to 8th,
    # and the UEL holder's to England's turn at the fill.
    uel = {r: placed[club("ENG", r)].route for r in range(1, 15) if club("ENG", r) in placed
           and placed[club("ENG", r)].competition == "UEL"}
    assert uel == {7: "league:ENG:7", 8: "league:ENG:8", 9: "fill:ENG"}


def test_a_cup_winner_from_lower_down_takes_its_place(monkeypatch: pytest.MonkeyPatch) -> None:
    outsider = 999_001  # a Championship club, say
    _fake(monkeypatch, cups={"FA_CUP": outsider})
    placed = _qualify()
    assert placed[outsider].competition == "UEL" and placed[outsider].route == "cup:FA_CUP"


def test_a_small_country_runs_out_and_the_fill_steps_in(monkeypatch: pytest.MonkeyPatch) -> None:
    global SMALL
    saved = SMALL
    SMALL = {**SMALL, "GRE": 2}  # Greece's 3rd and 4th places have nobody
    try:
        _fake(monkeypatch)
        placed = _qualify()
    finally:
        SMALL = saved
    assert club("GRE", 3) not in placed
    assert Counter(e.route.split(":")[0] for e in placed.values())["fill"] == 3 + 2


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


def test_a_first_season_qualifies_by_reputation(august: tuple[Engine, World]) -> None:
    engine, _ = august
    entries = _entries(engine)
    assert len({e.club_id for e in entries}) == len(entries) == 32 + 8 + 26 + 12 + 23 + 14
    with engine.connect() as conn:
        kinds = dict(conn.execute(select(competition.c.key, competition.c.type)).all())
        eng_top4 = {r.id for r in conn.execute(text(
            "SELECT c.id FROM club c JOIN club_league_membership m ON m.club_id = c.id "
            "JOIN competition k ON k.id = m.competition_id WHERE k.key = 'ENG1' "
            "AND m.season_id = 1 ORDER BY c.reputation DESC, c.id LIMIT 4"))}
        play_offs = conn.execute(select(fixture).where(
            fixture.c.season_id == 1, fixture.c.stage == "UCL", fixture.c.round == 0)).all()
    assert kinds["UCL"] == kinds["UEL"] == kinds["UECL"] == "continental"
    english = {e.club_id for e in entries if e.route.startswith("league:ENG:")
               and e.key == "UCL"}
    assert english == eng_top4
    assert len(play_offs) == 8  # 4 ties, two legs
    assert {p.date for p in play_offs} <= {"2026-08-18", "2026-08-19", "2026-08-25",
                                           "2026-08-26"}


def test_the_play_off_round_sends_winners_up_and_losers_down(
        august: tuple[Engine, World]) -> None:
    engine, world = august
    with engine.begin() as conn:
        while read_meta(conn).current_date < date(2026, 9, 1):
            career.advance(conn, world, max_days=(date(2026, 9, 1)
                                                  - read_meta(conn).current_date).days)
    entries = _entries(engine)
    assert all(e.stage == "league_phase" for e in entries)
    assert Counter(e.key for e in entries) == {"UCL": 36, "UEL": 36, "UECL": 36}
    dropped = Counter(e.route for e in entries if e.route.startswith("dropped:"))
    assert dropped == {"dropped:UCL": 4, "dropped:UEL": 6}
    with engine.connect() as conn:
        ties = conn.execute(select(cup_tie).join(
            competition, competition.c.id == cup_tie.c.competition_id).where(
            competition.c.type == "continental")).all()
    assert len(ties) == 4 + 6 + 7 and all(t.winner_club_id for t in ties)


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
        runs.append(sorted((e.key, e.club_id, e.stage, e.route) for e in _entries(engine)))
    assert runs[0] == runs[1]
