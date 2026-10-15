"""W6 E4 on the real world: a whole watch-only season with the European competitions on, and
the start of the next. Each competition's knockouts run from the play-off (9th to 24th) to a
one-match final, seeded from the league phase; the money is paid by round reached; the
season's coefficient points are kept; and next season the winners take their holders' places.
Needs the built world (takes a few minutes: a whole season of every league)."""

import shutil
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date
from typing import Any

import pytest
from sqlalchemy import Engine, select

from footsim.api.queries import _club_names, _competitions, cup_runs
from footsim.api.season_review import _continental_titles, season_final
from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.persistence.schema import (
    club_coefficient,
    competition,
    continental_entry,
    cup_tie,
    finance_ledger,
    fixture,
    league_final,
)
from footsim.world import career
from footsim.world.context import World, get_world
from footsim.world.cups import REST_DAYS
from footsim.world.europe.common import KNOCKOUT
from footsim.world.meta import read_meta

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


@pytest.fixture(scope="module")
def two_seasons(tmp_path_factory: pytest.TempPathFactory) -> tuple[Engine, World]:
    base = get_world()
    world = replace(base, defs=replace(base.defs, europe=base.defs.europe.model_copy(
        update={"enabled": True})))
    path = tmp_path_factory.mktemp("europe-season") / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        career.initialize_career(conn, world, None, None, seed=17)
    for _ in range(50):
        with engine.begin() as conn:
            career.advance(conn, world, max_days=400)
            if read_meta(conn).season_id == 2:
                break
    return engine, world


def _comp_id(engine: Engine, key: str) -> int:
    with engine.connect() as conn:
        found: int = conn.execute(select(competition.c.id).where(competition.c.key == key)
                                  ).scalar_one()
        return found


def _entries(engine: Engine, season: int, key: str) -> list[Any]:
    with engine.connect() as conn:
        return list(conn.execute(select(continental_entry).where(
            continental_entry.c.season_id == season,
            continental_entry.c.competition_id == _comp_id(engine, key))).all())


@pytest.mark.parametrize("key", ["UCL", "UEL", "UECL"])
def test_the_knockouts_run_to_a_final(two_seasons: tuple[Engine, World], key: str) -> None:
    engine, world = two_seasons
    comp = world.defs.continental[key]
    position = {e.club_id: e.position for e in _entries(engine, 1, key)}
    with engine.connect() as conn:
        ties = conn.execute(select(cup_tie).where(
            cup_tie.c.season_id == 1, cup_tie.c.competition_id == _comp_id(engine, key),
            cup_tie.c.round >= KNOCKOUT).order_by(cup_tie.c.round, cup_tie.c.id)).all()
        games = conn.execute(select(fixture).where(
            fixture.c.season_id == 1, fixture.c.stage == key,
            fixture.c.round >= KNOCKOUT)).all()
    by_round = [[t for t in ties if t.round == KNOCKOUT + k] for k in range(len(comp.knockout))]
    assert [len(r) for r in by_round] == [8, 8, 4, 2, 1]
    assert all(t.winner_club_id for t in ties) and all(g.status == "played" for g in games)
    playoff = {position[c] for t in by_round[0] for c in (t.club_a_id, t.club_b_id)}
    assert playoff == set(range(9, 25))
    assert {position[t.club_a_id] + position[t.club_b_id] for t in by_round[0]} == {33}
    last16 = {c for t in by_round[1] for c in (t.club_a_id, t.club_b_id)}
    assert {position[c] for c in last16 if position[c] <= 8} == set(range(1, 9))
    assert last16 - {c for c in last16 if position[c] <= 8} == {
        t.winner_club_id for t in by_round[0]}
    for k, rnd in enumerate(by_round[1:], start=1):  # every winner goes on to the next round
        if k + 1 < len(by_round):
            assert {t.winner_club_id for t in rnd} == {
                c for t in by_round[k + 1] for c in (t.club_a_id, t.club_b_id)}
    for t in ties:  # the better-placed club at home in the second leg
        legs = sorted((g for g in games if g.round == t.round and g.tie == t.tie),
                      key=lambda g: g.leg or 1)
        assert len(legs) == comp.knockout[t.round - KNOCKOUT].legs
        if len(legs) == 2:
            assert position[legs[1].home_club_id] < position[legs[1].away_club_id]
    final = [g for g in games if g.round == KNOCKOUT + len(comp.knockout) - 1]
    assert len(final) == 1 and final[0].neutral == 1


def test_the_money_and_the_coefficients(two_seasons: tuple[Engine, World]) -> None:
    engine, world = two_seasons
    with engine.connect() as conn:
        for key, comp in world.defs.continental.items():
            prize = world.defs.finance.europe_prizes[key]
            final = conn.execute(select(cup_tie).where(
                cup_tie.c.season_id == 1, cup_tie.c.competition_id == _comp_id(engine, key),
                cup_tie.c.round == KNOCKOUT + len(comp.knockout) - 1)).one()
            champion = final.winner_club_id
            entries = conn.execute(select(finance_ledger.c.amount_cents).where(
                finance_ledger.c.club_id == champion, finance_ledger.c.season_id == 1,
                finance_ledger.c.ref_id == _comp_id(engine, key),
                finance_ledger.c.kind == "prize")).scalars().all()
            assert round(prize.winner * 100) in entries
            assert round(prize.rounds[-1] * 100) in entries  # reaching the final
        points = dict(conn.execute(select(club_coefficient.c.club_id, club_coefficient.c.points)
                                   .where(club_coefficient.c.season_id == 1)).all())
    # Every club that played in Europe has its season's points (115 entered in all).
    assert len(points) == 32 + 8 + 26 + 12 + 23 + 14
    assert all(p >= 0 for p in points.values())


def test_next_season_the_winners_hold_their_places(two_seasons: tuple[Engine, World]) -> None:
    engine, world = two_seasons
    with engine.connect() as conn:
        winners = {}
        for key, comp in world.defs.continental.items():
            winners[key] = conn.execute(select(cup_tie.c.winner_club_id).where(
                cup_tie.c.season_id == 1, cup_tie.c.competition_id == _comp_id(engine, key),
                cup_tie.c.round == KNOCKOUT + len(comp.knockout) - 1)).scalar_one()
        entry = {r.club_id: r for r in conn.execute(select(
            continental_entry, competition.c.key).join(
            competition, competition.c.id == continental_entry.c.competition_id).where(
            continental_entry.c.season_id == 2))}
        champions = {r.competition_id: r.club_id for r in conn.execute(select(league_final).where(
            league_final.c.season_id == 1, league_final.c.position == 1))}
    assert entry[winners["UCL"]].key == "UCL" and entry[winners["UCL"]].route == "holder:UCL"
    assert entry[winners["UEL"]].key == "UCL"
    assert entry[winners["UECL"]].key in ("UCL", "UEL")
    # Last season's English champions are first among England's places.
    eng1 = _comp_id(engine, "ENG1")
    assert entry[champions[eng1]].key == "UCL"
    assert Counter(r.key for r in entry.values()) == {"UCL": 40, "UEL": 38, "UECL": 37}


def test_european_matches_have_room_all_season(two_seasons: tuple[Engine, World]) -> None:
    """Knockouts included: no club plays the day before or after a European match, and few
    with only one clear day (REST_DAYS is the rule; one day the crowded season's fallback)."""
    engine, world = two_seasons
    with engine.connect() as conn:
        rows = conn.execute(select(fixture.c.date, fixture.c.stage, fixture.c.home_club_id,
                                   fixture.c.away_club_id).where(fixture.c.season_id == 1)).all()
    days: dict[int, list[tuple[date, bool]]] = defaultdict(list)
    for r in rows:
        for c in (r.home_club_id, r.away_club_id):
            days[c].append((date.fromisoformat(r.date), r.stage in world.defs.continental))
    gaps = [((d2 - d1).days, c, d1.isoformat(), d2.isoformat())
            for c, games in days.items()
            for (d1, e1), (d2, e2) in zip(sorted(games), sorted(games)[1:], strict=False)
            if e1 or e2]
    # Never back to back; one clear day only now and then, when a crowded season has no other.
    assert not [g for g in gaps if g[0] < 2], [g for g in gaps if g[0] < 2][:10]
    tight = [g for g in gaps if g[0] <= REST_DAYS]
    assert len(tight) <= 0.02 * len(gaps), (len(tight), len(gaps), tight[:10])


def test_the_season_summary_leads_with_the_european_winners(
        two_seasons: tuple[Engine, World]) -> None:
    engine, world = two_seasons
    with engine.connect() as conn:
        heads = _continental_titles(conn, world, 1, _competitions(conn), _club_names(conn))
    assert [h.competition for h in heads] == [
        "UEFA Champions League", "UEFA Europa League", "UEFA Conference League"]
    assert all(h.kind == "continental_title" and h.text.endswith(f"win the {h.competition}.")
               and (h.detail or "").startswith("They beat ") for h in heads)


def test_a_european_clubs_season_end_and_history(two_seasons: tuple[Engine, World]) -> None:
    """The season summary and a club's cup runs read past European ties (they once broke)."""
    engine, world = two_seasons
    with engine.connect() as conn:
        winner = conn.execute(select(cup_tie.c.winner_club_id).where(
            cup_tie.c.season_id == 1, cup_tie.c.competition_id == _comp_id(engine, "UCL"),
            cup_tie.c.round == KNOCKOUT + 4)).scalar_one()
        runs = cup_runs(conn, world, winner)
        final = season_final(conn, world, winner, [])
    assert all(r.key in world.defs.cups for season_runs in runs.values() for r in season_runs)
    assert final is not None
