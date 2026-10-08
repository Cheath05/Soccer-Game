"""A place in the first team is rewarded in development (development.yaml), on the real base
world: a substitute named for a match who never comes on is credited bench minutes when the
result is recorded, whichever engine played it, and they count towards a young player's growth
and fade every month; an academy product who plays regularly has his potential raised.

Skipped when the base world hasn't been built (it needs the locally downloaded EA FC 27 file,
which isn't in the repository)."""

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from sqlalchemy import Connection, Engine, bindparam, select, text

from footsim.api.queries import player_detail
from footsim.core.paths import data_dir
from footsim.defs.positions import PositionGroup
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.persistence.schema import fixture, player_match
from footsim.world.career import agent_match, initialize_career, play_fixture
from footsim.world.context import get_world
from footsim.world.meta import read_meta
from footsim.world.results import credit_bench, record_result
from footsim.world.season import develop_players

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


@pytest.fixture(scope="module")
def career(tmp_path_factory: pytest.TempPathFactory) -> Engine:
    path = Path(tmp_path_factory.mktemp("first-team")) / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, get_world(), None, None, seed=5)
    return engine


@contextmanager
def _scratch(career: Engine) -> Iterator[Connection]:
    """A transaction that's rolled back afterwards: whatever happens in it is thrown away."""
    with career.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()


@pytest.fixture
def conn(career: Engine) -> Iterator[Connection]:
    """Every test starts from the same world."""
    with _scratch(career) as connection:
        yield connection


def _bench_minutes(conn: Connection) -> dict[int, float]:
    return {r.player_id: r.bench_minutes for r in conn.execute(text(
        "SELECT player_id, bench_minutes FROM player_state WHERE bench_minutes != 0"))}


def _first_fixture(conn: Connection) -> Any:
    return conn.execute(select(fixture).where(fixture.c.status == "scheduled")
                        .order_by(fixture.c.date, fixture.c.id)).first()


# --- the bench credit ---------------------------------------------------------------------


def test_unused_substitutes_are_credited_when_a_quick_match_is_recorded(conn: Connection) -> None:
    world = get_world()
    meta = read_meta(conn)
    credit = world.defs.development.bench_credit_minutes
    assert credit > 0 and _bench_minutes(conn) == {}  # nobody has any yet
    fx = _first_fixture(conn)
    report = play_fixture(conn, world, meta, fx, date.fromisoformat(fx.date))

    assert len(report.bench) >= 14  # two matchday squads' substitutes
    unused = {p for p in report.bench if p not in report.players}
    came_on = {p for p, line in report.players.items() if not line.started}
    assert unused and unused.isdisjoint(came_on)
    assert came_on <= set(report.bench)  # a substitute who came on is a named substitute too
    # Exactly the substitutes who never came on were credited, each by the YAML amount.
    assert _bench_minutes(conn) == dict.fromkeys(unused, credit)
    # Starters, and substitutes who came on, played real minutes instead.
    played = {r.player_id for r in conn.execute(text("SELECT player_id FROM player_match"))}
    assert played == set(report.players) and played.isdisjoint(unused)
    # And it adds up, match after match (the same squad named again).
    credit_bench(conn, report)
    assert _bench_minutes(conn) == dict.fromkeys(unused, 2 * credit)


def test_unused_substitutes_are_credited_when_an_agent_match_is_recorded(conn: Connection) -> None:
    """The agent engine (the user's matches, instant or watched) names its bench in its report."""
    world = get_world()
    meta = read_meta(conn)
    credit = world.defs.development.bench_credit_minutes
    fx = _first_fixture(conn)
    day = date.fromisoformat(fx.date)
    engine = agent_match(conn, world, meta, fx, day, record=False)
    home = engine.sheets[0]
    out = next(sp for sp in home.starters if sp.group is not PositionGroup.GK)
    on = next(sp for sp in home.bench if sp.group is not PositionGroup.GK)
    engine.substitute(0, out.player_id, on.player_id)  # play is stopped before kick-off
    engine.run(max_ticks=6000)  # ten minutes is enough to record
    report = engine.report()
    record_result(conn, fx.id, report, day, "instant")

    named = {sp.player_id for sheet in engine.sheets for sp in sheet.bench}
    assert set(report.bench) == named and len(named) >= 14
    assert on.player_id in report.players and not report.players[on.player_id].started
    credited = _bench_minutes(conn)
    assert credited == dict.fromkeys(named - {on.player_id}, credit)  # not the one who came on
    assert out.player_id not in credited  # nor a starter


# --- the bench credit fades, and speeds a young player's growth ---------------------------

MONTH_DAY = date(2026, 8, 1)


def _develop_with_bench(career: Engine, bench: float) -> dict[str, Any]:
    """One month's development of every player from the same start, after crediting each of
    them ``bench`` bench minutes. Nothing is kept."""
    world = get_world()
    with _scratch(career) as connection:
        connection.execute(text("UPDATE player_state SET bench_minutes = :b"), {"b": bench})
        develop_players(connection, world, read_meta(connection), MONTH_DAY, 1 / 12)
        ages = {r.id: (MONTH_DAY - date.fromisoformat(r.birth_date)).days / 365.25
                for r in connection.execute(text("SELECT id, birth_date FROM person"))}
        progress = dict(connection.execute(text(
            "SELECT player_id, progress FROM player_development")).all())
        left = connection.execute(text(
            "SELECT MIN(bench_minutes) AS low, MAX(bench_minutes) AS high "
            "FROM player_state")).one()
        attrs = [tuple(r) for r in connection.execute(text(
            "SELECT * FROM player_attr ORDER BY player_id"))]
    return {"ages": ages, "progress": progress, "left": (left.low, left.high), "attrs": attrs}


def test_the_bench_credit_fades_each_month_and_speeds_the_young_up(career: Engine) -> None:
    rules = get_world().defs.development
    none = _develop_with_bench(career, 0.0)
    again = _develop_with_bench(career, 0.0)
    credited = _develop_with_bench(career, 900.0)
    assert again["progress"] == none["progress"] and again["attrs"] == none["attrs"]  # no luck

    # It fades by the YAML share in the month's development, and nothing appears from nowhere.
    assert none["left"] == (0, 0)
    assert credited["left"] == pytest.approx((900.0 * rules.bench_decay,) * 2)

    ids = sorted(none["progress"])
    age = np.array([none["ages"][i] for i in ids])
    base = np.array([none["progress"][i] for i in ids])
    gain = np.array([credited["progress"][i] for i in ids]) - base
    young = age < 22
    assert young.sum() > 1000
    assert gain[young].mean() > 0 and np.mean(gain[young] > 0) > 0.5  # most grow faster
    # None grows slower. (Progress falls by a point whenever it makes a whole-point step, so
    # look at those a long way from one.)
    safe = young & (np.abs(base) < 0.3)
    assert safe.sum() > 500 and gain[safe].min() > -1e-9
    past_peak = age >= 30  # minutes only matter before a player's peak
    assert past_peak.sum() > 1000 and np.all(gain[past_peak] == 0)


# --- the academy boost --------------------------------------------------------------------


def _players(conn: Connection, born_after: str, born_before: str, count: int) -> list[Any]:
    return list(conn.execute(text("""
        SELECT p.id, k.club_id, pl.pa_hidden FROM person p JOIN player pl ON pl.person_id = p.id
        JOIN contract k ON k.person_id = p.id AND k.is_active = 1 AND k.kind = 'player'
        WHERE p.birth_date > :after AND p.birth_date < :before AND pl.pa_hidden BETWEEN 60 AND 85
          AND pl.retired_on IS NULL ORDER BY p.id LIMIT :n"""),
        {"after": born_after, "before": born_before, "n": count}))


def _play_matches(conn: Connection, player_id: int, club_id: int, matches: int) -> None:
    """As if he had played ``matches`` full league matches last autumn and winter."""
    games = conn.execute(text(
        "SELECT id FROM fixture WHERE date BETWEEN '2026-10-01' AND '2027-04-30' "
        "ORDER BY date, id LIMIT :n"), {"n": matches}).scalars().all()
    conn.execute(player_match.insert(), [
        {"fixture_id": g, "player_id": player_id, "club_id": club_id, "started": 1,
         "minutes": 90, "rating": 6.5} for g in games])


def _contract(conn: Connection, player_id: int, club_id: int, kind: str, active: bool) -> None:
    conn.execute(text(
        "INSERT INTO contract (person_id, club_id, kind, start_date, end_date, "
        "wage_weekly_cents, is_active) VALUES (:p, :c, :kind, '2022-07-01', '2028-06-30', 100, :a)"
    ), {"p": player_id, "c": club_id, "kind": kind, "a": int(active)})


def _academy_scenario(conn: Connection) -> dict[str, Any]:
    """Seven players, each a different case, all played the same four months of development.
    Returns what became of each: (potential before, potential after, boost so far), and the
    scouting range of the one the boost is meant for, before and after."""
    world = get_world()
    meta = read_meta(conn)
    young = _players(conn, "2006-06-01", "2009-01-01", 6)  # 18 to 20 on the first day below
    elder = _players(conn, "1999-01-01", "2002-01-01", 1)[0]  # 25 to 28
    assert len(young) == 6
    regular, benched, senior, elsewhere, graduated, loaned = young
    other = int(conn.execute(text("SELECT id FROM club WHERE id NOT IN (:a, :b, :c) "
                                  "ORDER BY id LIMIT 1"),
                             {"a": elsewhere.club_id, "b": loaned.club_id,
                              "c": elder.club_id}).scalar_one())

    # Academy products are on a youth contract with the club they play for, or had one.
    for player in (regular, benched, loaned, elder):
        conn.execute(text("UPDATE contract SET kind = 'youth' WHERE person_id = :p "
                          "AND is_active = 1"), {"p": player.id})
    _contract(conn, graduated.id, graduated.club_id, "youth", active=False)  # then a senior one
    _contract(conn, elsewhere.id, other, "youth", active=False)  # his academy is another club
    _contract(conn, loaned.id, other, "loan", active=True)  # an academy product, but loaned out
    for player in (regular, senior, elsewhere, graduated, elder):
        _play_matches(conn, player.id, player.club_id, 23)  # 2,070 minutes
    _play_matches(conn, loaned.id, other, 23)  # for the club he is on loan at
    _play_matches(conn, benched.id, benched.club_id, 5)  # 450

    before = player_detail(conn, world, regular.id).potential
    for day in (date(2027, 5, 1), date(2027, 6, 1), date(2027, 7, 1), date(2027, 8, 1)):
        develop_players(conn, world, meta, day, 1 / 12)
    after = player_detail(conn, world, regular.id).potential

    named = {"regular": regular, "benched": benched, "senior": senior, "elsewhere": elsewhere,
             "graduated": graduated, "loaned": loaned, "elder": elder}
    now = {r.person_id: (r.pa_hidden, r.potential_boost) for r in conn.execute(text(
        "SELECT pl.person_id, pl.pa_hidden, d.potential_boost FROM player pl "
        "JOIN player_development d ON d.player_id = pl.person_id "
        "WHERE pl.person_id IN :ids").bindparams(bindparam("ids", expanding=True)),
        {"ids": [p.id for p in named.values()]})}
    return {"players": {name: (p.pa_hidden, *now[p.id]) for name, p in named.items()},
            "range": ((before.low, before.high), (after.low, after.high))}


def test_an_academy_regular_has_his_potential_raised_each_month(career: Engine) -> None:
    with _scratch(career) as conn:
        result = _academy_scenario(conn)
    with _scratch(career) as conn:
        assert _academy_scenario(conn) == result  # the same every time

    assert get_world().defs.development.academy_boost_per_year == 3  # 4 months: a whole point
    players = result["players"]
    assert players["regular"] == (players["regular"][0], players["regular"][0] + 1, 1.0)
    assert players["graduated"] == (players["graduated"][0], players["graduated"][0] + 1, 1.0)
    for name in ("benched", "senior", "elsewhere", "loaned", "elder"):
        assert players[name][1:] == (players[name][0], 0.0), name
    # i.e. the regular and the one who had a youth contract with his club are raised a point;
    # not the academy product who's on the bench (benched), the regular who never came up
    # through the academy (senior), the one whose academy was another club (elsewhere), the one
    # lent to another club (loaned), or the one too old for it (elder).

    # The scouting estimate reads the raised potential: the range moves up a point with it.
    (low, high), (low_after, high_after) = result["range"]
    assert high_after == high + 1 and low_after >= low
