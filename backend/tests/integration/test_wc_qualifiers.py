"""The World Cup 2030 qualifiers (W8 I3, world/international/qualifiers.py), run quickly: each
stage is drawn on its day, its results are filled in (the stronger team by Elo wins, except a
few draws in the groups), path finals follow their semi-finals, and the outcomes are recorded.
Every stage's matches fit its windows, every team plays at most once a day, and exactly 48 teams
reach the finals: the hosts, then each confederation's share and two from the intercontinental
play-off. Needs the built world."""

import shutil
from collections import Counter
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from footsim.api.app import create_app
from footsim.api.session import CareerSession
from footsim.core.paths import data_dir
from footsim.match.report import MatchEvent, MatchReport, PlayerLine
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.world.career import initialize_career, is_international
from footsim.world.context import World, get_world
from footsim.world.international.qualifiers import (
    STAGE,
    _Teams,
    draw_day,
    group_tables,
    qualified_teams,
    qualifiers_day,
    stage_days,
)
from footsim.world.international.windows import match_kind
from footsim.world.meta import read_meta
from footsim.world.results import record_result
from footsim.world.season import decider_for

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")

SHARES = {"UEFA": 16, "CONMEBOL": 6, "CAF": 9, "AFC": 8, "CONCACAF": 6, "OFC": 1}


def _play(conn: object, key: str) -> None:
    """Every scheduled fixture of the stage: the higher Elo wins 2-0, or 1-1 if within 15
    points in a group (a path's level match goes to the higher Elo on penalties)."""
    teams = _Teams.load(conn)  # type: ignore[arg-type]
    rows = conn.execute(text(  # type: ignore[attr-defined]
        "SELECT id, home_club_id, away_club_id, tie FROM fixture WHERE stage = :s "
        "AND status = 'scheduled'"), {"s": STAGE + key}).all()
    for f in rows:
        home, away = teams.elo[f.home_club_id], teams.elo[f.away_club_id]
        group = "-" not in (f.tie or "")
        if group and abs(home - away) < 15:
            hg, ag, hp, ap = 1, 1, None, None
        else:
            hg, ag = (2, 0) if home >= away else (0, 2)
            hp = ap = None
        conn.execute(text(  # type: ignore[attr-defined]
            "UPDATE fixture SET status = 'played', home_goals = :hg, away_goals = :ag, "
            "home_pens = :hp, away_pens = :ap, sim = 'test' WHERE id = :i"),
            {"hg": hg, "ag": ag, "hp": hp, "ap": ap, "i": f.id})


@pytest.fixture(scope="module")
def cycle(tmp_path_factory: pytest.TempPathFactory) -> tuple[Engine, World, list[str]]:
    world = get_world()
    path = tmp_path_factory.mktemp("wcq") / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, world, None, None, seed=29)
    news: list[str] = []
    stages = world.defs.international.qualifiers.stages
    with engine.begin() as conn:
        meta = read_meta(conn)
        for stage in sorted(stages, key=lambda s: draw_day(world, meta, s)):
            news += qualifiers_day(conn, world, meta, draw_day(world, meta, stage))
            for _ in range(3):  # semi-finals, then finals
                _play(conn, stage.key)
                news += qualifiers_day(conn, world, meta, stage_days(world, meta, stage)[-1])
    return engine, world, news


def test_each_stage_fits_its_windows(cycle: tuple[Engine, World, list[str]]) -> None:
    engine, world, _ = cycle
    with engine.connect() as conn:
        meta = read_meta(conn)
        for stage in world.defs.international.qualifiers.stages:
            days = {d.isoformat() for d in stage_days(world, meta, stage)}
            rows = conn.execute(text("SELECT date FROM fixture WHERE stage = :s"),
                                {"s": STAGE + stage.key}).all()
            assert rows, stage.key
            assert {r.date for r in rows} <= days, stage.key
        # No team plays twice on a day.
        clash = conn.execute(text(
            "SELECT date, c, COUNT(*) n FROM (SELECT date, home_club_id c FROM fixture "
            "WHERE stage LIKE 'WCQ:%' UNION ALL SELECT date, away_club_id FROM fixture "
            "WHERE stage LIKE 'WCQ:%') GROUP BY 1, 2 HAVING n > 1")).all()
        assert clash == []


def test_groups_are_drawn_from_elo_pots(cycle: tuple[Engine, World, list[str]]) -> None:
    engine, _, _ = cycle
    with engine.connect() as conn:
        teams = _Teams.load(conn)
        uefa = group_tables(conn, "UEFA_G", teams)
        assert len(uefa) == 12 and sorted(len(t) for t in uefa.values()) == [4] * 8 + [5] * 4
        assert all(r.played == 2 * (len(t) - 1) for t in uefa.values() for r in t)
        # The 12 best UEFA teams are in 12 different groups (pot 1).
        best = sorted((c for c, conf in teams.confederation.items() if conf == "UEFA"
                       and teams.code[c] not in ("ESP", "POR")), key=lambda c: -teams.elo[c])[:12]
        group_of = {r.club_id: g for g, t in uefa.items() for r in t}
        assert len({group_of[c] for c in best}) == 12
        conmebol = group_tables(conn, "CONMEBOL", teams)
        assert [len(t) for t in conmebol.values()] == [10]
        assert all(r.played == 18 for r in conmebol["A"])


def test_48_teams_qualify(cycle: tuple[Engine, World, list[str]]) -> None:
    engine, _, news = cycle
    with engine.connect() as conn:
        teams = _Teams.load(conn)
        through = qualified_teams(conn)
        assert len(through) == 48
        assert {"ESP", "POR", "MAR"} <= set(through) and through["ESP"] == "Hosts"
        by_code = {code: c for c, code in teams.code.items()}
        per = Counter(teams.confederation[by_code[code]] for code in through)
        ic = sum(1 for how in through.values() if how == "Intercontinental play-off")
        assert ic == 2
        for conf, share in SHARES.items():
            # Each confederation's share, plus any intercontinental play-off winners of its own.
            extra = sum(1 for code, how in through.items() if how == "Intercontinental play-off"
                        and teams.confederation[by_code[code]] == conf)
            assert per[conf] == share + extra, conf
    assert any(m.startswith("World Cup 2030:") for m in news)


def test_international_cards_dont_ban_players_for_their_clubs(
        cycle: tuple[Engine, World, list[str]]) -> None:
    engine, world, _ = cycle
    with engine.begin() as conn:
        fx = conn.execute(text("SELECT * FROM fixture WHERE stage = 'WCQ:CONMEBOL' LIMIT 1")
                          ).one()
        assert is_international(conn, fx)
        pid = int(conn.execute(text("SELECT player_id FROM national_squad WHERE club_id = :c "
                                    "LIMIT 1"), {"c": fx.home_club_id}).scalar_one())
        report = MatchReport(fx.home_club_id, fx.away_club_id, home_goals=1, away_goals=0)
        report.players[pid] = PlayerLine(pid, fx.home_club_id, started=True, minutes=60, red=1)
        report.events.append(MatchEvent(60, "red", fx.home_club_id, pid, detail="straight red"))
        before = conn.execute(text("SELECT suspended_matches FROM player_state "
                                   "WHERE player_id = :p"), {"p": pid}).scalar_one()
        record_result(conn, fx.id, report, date(2027, 9, 23), "quick", discipline=False)
        after = conn.execute(text("SELECT suspended_matches FROM player_state "
                                  "WHERE player_id = :p"), {"p": pid}).scalar_one()
        assert after == before
        conn.rollback()


def test_knockout_rules_and_elo_weights(cycle: tuple[Engine, World, list[str]]) -> None:
    engine, world, _ = cycle
    assert match_kind("WCQ:UEFA_G") == "qualifier" and match_kind("INTL_FRIENDLY") == "friendly"
    assert match_kind("WCF:G") == "finals"
    with engine.connect() as conn:
        group = conn.execute(text("SELECT * FROM fixture WHERE stage = 'WCQ:UEFA_G' LIMIT 1")
                             ).one()
        assert decider_for(conn, world, group) is None
        single = conn.execute(text("SELECT * FROM fixture WHERE stage = 'WCQ:UEFA_PO' LIMIT 1")
                              ).one()
        rules = decider_for(conn, world, single)
        assert rules is not None and rules.penalties and rules.first_leg is None
        first, second = conn.execute(text(
            "SELECT * FROM fixture WHERE stage = 'WCQ:AFC_R5' ORDER BY leg")).all()
        assert decider_for(conn, world, first) is None
        two = decider_for(conn, world, second)
        assert two is not None and two.first_leg is not None


def test_the_qualifiers_page_at_the_start(tmp_path: Path) -> None:
    client = TestClient(create_app(session=CareerSession(tmp_path / "saves", BASE_WORLD),
                                   frontend=None))
    league = next(lg for lg in client.get("/api/world/leagues").json() if lg["key"] == "ENG4")
    client.post("/api/saves/1/new", json={"club_id": league["clubs"][0]["id"],
                                          "manager_name": "Tester"})
    view = client.get("/api/international/qualifiers").json()
    assert view["cycle"] == 2030 and len(view["stages"]) == 13
    assert not any(s["drawn"] for s in view["stages"])
    # The hosts are through once the qualifiers have started; nobody before.
    assert view["qualified"] == [] or {q["how"] for q in view["qualified"]} == {"Hosts"}
