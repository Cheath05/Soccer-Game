"""A club's European record and honours, and the Treble. The season's matches aren't played:
the league tables, cup ties and European ties are written as if they had been, which is all the
club history reads. Skipped when the base world hasn't been built (it needs the locally
downloaded EA FC 27 file, which isn't in the repository)."""

import shutil
from typing import Any

import pytest
from sqlalchemy import Engine, text

from footsim.api import queries
from footsim.api.honours import treble
from footsim.api.season_review import _headlines
from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.persistence.schema import (
    continental_entry,
    cup_tie,
    league_final,
    season,
)
from footsim.world import career
from footsim.world.context import World, get_world
from footsim.world.cups import cup_competition_id
from footsim.world.europe.common import KNOCKOUT, competition_id

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


def _final(season_id: int, comp_id: int, club_id: int, position: int,
           outcome: str | None) -> dict[str, Any]:
    return {"season_id": season_id, "competition_id": comp_id, "club_id": club_id,
            "position": position, "played": 38, "won": 20, "drawn": 8, "lost": 10,
            "goals_for": 60, "goals_against": 40, "points": 68, "outcome": outcome}


def _tie(season_id: int, comp_id: int, round_: int, a: int, b: int | None, winner: int | None,
         tie: str = "1") -> dict[str, Any]:
    return {"season_id": season_id, "competition_id": comp_id, "round": round_, "tie": tie,
            "club_a_id": a, "club_b_id": b, "winner_club_id": winner}


@pytest.fixture(scope="module")
def career_db(tmp_path_factory: pytest.TempPathFactory) -> tuple[Engine, World, int, int]:
    """Club A: the Treble in 2026-27, a Champions League qualifying exit into the Europa
    League's league phase in 2027-28, the Champions League and the league (no cup) in 2028-29.
    Club B beat it in two finals."""
    world = get_world()
    path = tmp_path_factory.mktemp("honours") / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        career.initialize_career(conn, world, None, None, seed=5)
        a, b = (r.club_id for r in conn.execute(text(
            "SELECT m.club_id FROM club_league_membership m JOIN competition c ON "
            "c.id = m.competition_id WHERE c.key = 'ENG1' LIMIT 2")))
        eng1 = conn.execute(text("SELECT id FROM competition WHERE key = 'ENG1'")).scalar_one()
        ucl = competition_id(conn, world.defs.continental["UCL"])
        uel = competition_id(conn, world.defs.continental["UEL"])
        fa_cup = cup_competition_id(conn, world.defs.cups["FA_CUP"])
        final_round = len(world.defs.cups["FA_CUP"].rounds) - 1
        ucl_final = KNOCKOUT + len(world.defs.continental["UCL"].knockout) - 1
        conn.execute(season.insert(), [
            {"id": 2, "label": "2027-28", "start_date": "2027-07-01", "end_date": "2028-06-30"},
            {"id": 3, "label": "2028-29", "start_date": "2028-07-01", "end_date": "2029-06-30"}])
        conn.execute(league_final.insert(), [
            _final(1, eng1, a, 1, "champion"), _final(1, eng1, b, 2, None),
            _final(2, eng1, a, 5, None), _final(2, eng1, b, 1, "champion"),
            _final(3, eng1, a, 1, "champion"), _final(3, eng1, b, 2, None)])
        conn.execute(cup_tie.insert(), [
            _tie(1, fa_cup, final_round, a, b, a),
            _tie(1, ucl, ucl_final, a, b, a),
            _tie(1, ucl, KNOCKOUT + 1, a, b, a),
            _tie(2, fa_cup, final_round, b, a, b),
            _tie(2, ucl, -1, a, b, b),  # lost the third qualifying round
            _tie(3, fa_cup, final_round, b, a, b),
            _tie(3, ucl, ucl_final, b, a, a)])
        conn.execute(continental_entry.delete().where(  # the new career's own entries
            continental_entry.c.club_id.in_([a, b])))
        conn.execute(continental_entry.insert(), [
            {"season_id": 2, "competition_id": uel, "club_id": a, "stage": "league_phase",
             "route": "dropped:UCL", "position": 30}])
    return engine, world, a, b


def test_a_clubs_european_runs_and_trophies(career_db: tuple[Engine, World, int, int]) -> None:
    engine, world, a, _ = career_db
    with engine.connect() as conn:
        history = queries.club_history(conn, world, a)
    by_label = {s.season: s for s in history.seasons}
    assert [(r.key, r.reached, r.won) for r in by_label["2026-27"].europe] == [
        ("UCL", "Winners", True)]
    assert [(r.key, r.reached, r.out) for r in by_label["2027-28"].europe] == [
        ("UCL", "Third qualifying round", True), ("UEL", "League phase (30th)", True)]
    assert history.european_titles == 2
    europe_trophy = history.trophies[0]
    assert (europe_trophy.kind, europe_trophy.key, europe_trophy.seasons) == (
        "europe", "UCL", ["2026-27", "2028-29"])
    assert [(t.kind, t.key, t.seasons) for t in history.trophies[1:]] == [
        ("league", "ENG1", ["2026-27", "2028-29"]), ("cup", "FA_CUP", ["2026-27"])]


def test_the_treble_needs_the_league_the_cup_and_the_champions_league(
        career_db: tuple[Engine, World, int, int]) -> None:
    engine, world, a, b = career_db
    with engine.connect() as conn:
        history = queries.club_history(conn, world, a)
        found = [treble(conn, world, s) for s in (1, 2, 3)]
        other = queries.club_history(conn, world, b)
    assert history.treble_seasons == ["2026-27"]
    assert history.seasons[-1].treble_trophies == [
        "Premier League", "FA Cup", "UEFA Champions League"]
    assert [s.treble for s in history.seasons] == [False, False, True]  # newest first
    first = found[0]
    assert first is not None and (first.club_id, first.league) == (a, "Premier League")
    assert found[1] is None and found[2] is None  # 2028-29: no cup
    assert other.treble_seasons == [] and other.european_titles == 0


def test_the_season_summary_headlines_the_treble(
        career_db: tuple[Engine, World, int, int]) -> None:
    engine, world, a, _ = career_db
    with engine.connect() as conn:
        heads = _headlines(conn, world, 1, queries._competitions(conn), queries._club_names(conn))
        none = _headlines(conn, world, 3, queries._competitions(conn), queries._club_names(conn))
    assert heads[0].kind == "treble" and heads[0].club.id == a
    assert heads[0].trophies == ["Premier League", "FA Cup", "UEFA Champions League"]
    assert "treble" not in {h.kind for h in none}
