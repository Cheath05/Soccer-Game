"""A college coach's recruiting (W9c) on the base world: the target list and the staff's effort
(interest and knowledge grow, the estimate narrows), offers within the program's money and places
and the dates, the AI programs leaving the user's program alone, commitments to the user with
news, pulling a committed recruit's offer, signing day, and the user's signed class enrolling
as freshmen. The year runs without the matches. Needs the built world."""

import shutil
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from footsim.core.paths import data_dir
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.world.career import initialize_career
from footsim.world.college import coach
from footsim.world.college import recruiting as rc
from footsim.world.context import World, get_world
from footsim.world.meta import CareerMeta, read_meta, write_meta

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")


@pytest.fixture(scope="module")
def career(tmp_path_factory: pytest.TempPathFactory) -> tuple[Engine, World]:
    path: Path = tmp_path_factory.mktemp("coach-recruiting") / "career.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    world = get_world()
    with engine.begin() as conn:
        initialize_career(conn, world, None, "Coach", seed=3,
                          college_program="Wake Forest Demon Deacons")
    return engine, world


def _days(engine: Engine, world: World, until: date) -> list[str]:
    """Recruiting day by day to ``until`` (the matches aren't played)."""
    news: list[str] = []
    with engine.begin() as conn:
        meta = read_meta(conn)
        day = meta.current_date
        while day < until:
            news += rc.progress_recruiting(conn, world, meta, day)
            day += timedelta(days=1)
        meta.current_date = day
        write_meta(conn, meta)
    return news


def _meta(engine: Engine) -> CareerMeta:
    with engine.connect() as conn:
        return read_meta(conn)


def test_the_assistant_recruits_the_leavers_replacements(career: tuple[Engine, World]) -> None:
    """The recruiting assistant (20 Nov; 22 Nov: by next season's squad): Top targets with
    offers, only at the position groups next season is short of a balanced roster, to realistic
    recruits, about ``overcommit`` per place; nothing twice; the user's own targets left alone.
    Once a group is covered it pulls its own open offers there. (Rolled back, so the recruiting
    year below starts as before.)"""
    import math

    from footsim.world.college import coach
    from footsim.world.college.assistant import needs, recruit_for_leavers, targets

    engine, world = career
    with engine.connect() as conn:
        tx = conn.begin()
        meta = read_meta(conn)
        meta.auto_recruiting = True
        meta.current_date = date(meta.current_date.year, 8, 3)  # offers are open
        need = needs(conn, world, meta)
        assert sum(need.values()) > 0 and set(need) <= set(targets(world))
        mine = next(v for v in coach.recruits(conn, world, meta) if v.fit == "good")
        coach.set_target(conn, world, meta, mine.id, rc.WATCH)
        news = recruit_for_leavers(conn, world, meta, meta.current_date)
        assert news and news[0].startswith("Your assistant offered")
        views = coach.recruits(conn, world, meta)
        offered = [v for v in views if v.offer_status == "open"]
        assert offered and all(v.priority == rc.TOP and v.fit in ("good", "reach")
                               for v in offered)
        by_group: dict[str, int] = {}
        for v in offered:
            g = str(world.defs.positions[v.position].group)
            by_group[g] = by_group.get(g, 0) + 1
        overcommit = world.defs.college.recruiting.assistant.overcommit
        assert all(g in need and n <= math.ceil(need[g] * overcommit)
                   for g, n in by_group.items())
        assert next(v for v in views if v.id == mine.id).priority == rc.WATCH
        meta = read_meta(conn)
        assert set(meta.assistant_offers) == {v.id for v in offered}
        assert recruit_for_leavers(conn, world, meta, meta.current_date) == []
        # A group covered by commitments (here, recruits made to commit): its offers are pulled.
        group, _ = max(by_group.items(), key=lambda kv: kv[1])
        positions = [p for p, d in world.defs.positions.items() if str(d.group) == group]
        marks = ",".join(f"'{p}'" for p in positions)
        conn.execute(text(
            f"UPDATE recruit SET status = 'committed', club_id = :c, share = 0 WHERE id IN "
            f"(SELECT id FROM recruit WHERE class_season = :s AND status = 'open' AND position "
            f"IN ({marks}) AND id NOT IN (SELECT recruit_id FROM recruit_offer WHERE club_id = "
            f":c) LIMIT :n)"),
            {"c": meta.user_club_id, "s": meta.season_id + 1, "n": need[group]})
        assert needs(conn, world, meta)[group] == 0
        news = recruit_for_leavers(conn, world, meta, meta.current_date)
        assert any(n.startswith("Your assistant withdrew") for n in news)
        still = [v for v in coach.recruits(conn, world, meta) if v.offer_status == "open"
                 and str(world.defs.positions[v.position].group) == group]
        assert still == []
        tx.rollback()


def test_a_recruiting_year(career: tuple[Engine, World]) -> None:
    engine, world = career
    with engine.begin() as conn:
        meta = read_meta(conn)
        s = coach.summary(conn, world, meta)
        assert s.phase == coach.PHASE_BEFORE and s.class_count == 0
        assert s.funding == world.defs.college.recruiting.programs.funding_by_tier[1]
        board = coach.recruits(conn, world, meta)
        assert len(board) == world.defs.college.recruiting.class_size
        with pytest.raises(coach.RecruitingError, match="Offers open on"):
            coach.make_offer(conn, world, meta, board[0].id, 1.0)
        # Targets: a few good recruits at the program's level, one a top priority.
        targets = [v for v in board if 60 <= v.national_rank <= 400][:8]
        for k, v in enumerate(targets):
            coach.set_target(conn, world, meta, v.id, "top" if k < 3 else "high")
        before = {v.id: v for v in coach.recruits(conn, world, meta, [v.id for v in targets])}
    _days(engine, world, date(2026, 8, 1))
    with engine.begin() as conn:
        meta = read_meta(conn)
        for v in targets:
            coach.make_offer(conn, world, meta, v.id, 0.5)
        s = coach.summary(conn, world, meta)
        assert s.phase == coach.PHASE_OPEN and s.open_offers == len(targets)
        assert s.offered_money == pytest.approx(0.5 * len(targets))
    with engine.begin() as conn:
        meta = read_meta(conn)
        # More than the money allows is refused.
        others = [v for v in coach.recruits(conn, world, meta) if v.priority is None][:40]
        with pytest.raises(coach.RecruitingError):
            for v in others:
                coach.make_offer(conn, world, meta, v.id, 1.0)
        conn.rollback()
    news = _days(engine, world, date(2026, 10, 1))
    with engine.connect() as conn:
        meta = read_meta(conn)
        after = {v.id: v for v in coach.recruits(conn, world, meta, [v.id for v in targets])}
        for v in targets:
            assert (after[v.id].interest or 0) > (before[v.id].interest or 0)
            assert after[v.id].knowledge > before[v.id].knowledge
            width = after[v.id].overall.high - after[v.id].overall.low
            assert width < before[v.id].overall.high - before[v.id].overall.low
        # The AI programs never make the user's program's offers.
        made = conn.execute(text(
            "SELECT COUNT(*) FROM recruit_offer WHERE club_id = :c"),
            {"c": meta.user_club_id}).scalar_one()
        assert made == len(targets)
    news += _days(engine, world, date(2027, 1, 15))
    with engine.connect() as conn:
        meta = read_meta(conn)
        mine = [v for v in coach.recruits(conn, world, meta, [v.id for v in targets])
                if v.committed_to and v.committed_to[0] == meta.user_club_id]
    assert mine, "no target committed to a tier-1 program offering half scholarships"
    assert any("commits to Wake Forest" in n for n in news)
    # Pulling a committed recruit's offer frees him and costs trust with the rest.
    with engine.begin() as conn:
        meta = read_meta(conn)
        pulled = mine[0]
        others_before = {v.id: v.interest for v in coach.recruits(conn, world, meta)
                         if v.priority is not None and v.id != pulled.id}
        said = coach.pull_offer(conn, world, meta, pulled.id)
        assert said and "trust" in said[0]
        again = coach.recruits(conn, world, meta, [pulled.id])[0]
        assert again.status == "open" and again.offer_status == "pulled"
        for v in coach.recruits(conn, world, meta, list(others_before)):
            if others_before[v.id]:
                assert (v.interest or 0) < (others_before[v.id] or 0)
    # Signing day and the close.
    news = _days(engine, world, date(2027, 5, 2))
    assert any(n.startswith("Signing day:") for n in news)
    with engine.connect() as conn:
        meta = read_meta(conn)
        assert coach.summary(conn, world, meta).phase == coach.PHASE_CLOSED
        signed = conn.execute(text(
            "SELECT id, share FROM recruit WHERE status = 'signed' AND club_id = :c"),
            {"c": meta.user_club_id}).all()
        assert signed and all(r.share == pytest.approx(0.5) for r in signed)
        ranks = coach.class_rankings(conn, world, meta)
        assert any(club_id == meta.user_club_id for club_id, *_ in ranks)
    with engine.begin() as conn:
        meta = read_meta(conn)
        joined = rc.enroll_class(conn, world, meta, 2, date(2027, 7, 1))
        assert joined >= len(signed)
        freshmen = conn.execute(text(
            "SELECT COUNT(*) FROM college_player cp JOIN recruit r ON r.player_id = cp.player_id "
            "WHERE cp.club_id = :c AND cp.class_year = 1 AND cp.scholarship = 0.5"),
            {"c": meta.user_club_id}).scalar_one()
        assert freshmen == len(signed)
        conn.rollback()


def test_the_estimate_narrows_to_the_truth() -> None:
    wide = coach.estimate(1, 5, "overall", 50.0, 0.0, 4.0, 7.0, 1.0)
    narrow = coach.estimate(1, 5, "overall", 50.0, 1.0, 4.0, 7.0, 1.0)
    assert wide.high - wide.low > narrow.high - narrow.low
    assert narrow.low <= 50 <= narrow.high
    assert coach.estimate(1, 5, "overall", 50.0, 0.0, 4.0, 7.0, 1.0) == wide  # seeded
