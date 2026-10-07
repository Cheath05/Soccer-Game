"""The season-end views on a small hand-made save: the season summary's structure, the player's
record by season and competition, and the season choices the League and Fixtures pages make."""

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, delete, select, update

from footsim.api import queries
from footsim.api.season_review import other_news, season_final, season_review
from footsim.domain.attributes import ATTRIBUTES
from footsim.persistence.database import create_database
from footsim.persistence.schema import (
    club,
    club_league_membership,
    competition,
    contract,
    cup_tie,
    fixture,
    game_meta,
    league_final,
    nation,
    person,
    player,
    player_attr,
    player_match,
    player_position,
    player_season_overall,
    playoff_tie,
    season,
)
from footsim.world.context import World, get_world
from footsim.world.overall_history import player_overalls, record_season_start

A, B, C, D, E = 1, 2, 3, 4, 5  # A is the user's: relegated from ENG1 at the end of season 1
P1, P2, P3, STAR, OLD, OTHER, FREE, YOUTH = 11, 12, 13, 14, 15, 16, 17, 18
ENG1, ENG2, FA_CUP = 1, 2, 3
NEW_SEASON = "2027-07-01"


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def _person(conn: Connection, pid: int, name: str, born: str, level: int, pa: int = 70,
            retired: str | None = None) -> None:
    conn.execute(person.insert().values(id=pid, first_name=name, last_name="Test",
                                        birth_date=born))
    conn.execute(player.insert().values(
        person_id=pid, preferred_foot="Right", weak_foot=3, skill_moves=2, pa_hidden=pa,
        reputation=50, retired_on=retired))
    conn.execute(player_attr.insert().values(player_id=pid, **dict.fromkeys(ATTRIBUTES, level)))
    conn.execute(player_position.insert(), [{"player_id": pid, "position": "CM",
                                             "familiarity": 20},
                                            {"player_id": pid, "position": "AM",
                                             "familiarity": 15}])


def _contract(conn: Connection, pid: int, club_id: int, active: bool = True,
              kind: str = "player", start: str = "2026-07-01", end: str = "2029-06-30") -> None:
    conn.execute(contract.insert().values(
        person_id=pid, club_id=club_id, kind=kind, start_date=start, end_date=end,
        wage_weekly_cents=100_000, is_active=int(active)))


def _final(season_id: int, comp: int, club_id: int, position: int,
           outcome: str | None) -> dict[str, Any]:
    return {"season_id": season_id, "competition_id": comp, "club_id": club_id,
            "position": position, "played": 38, "won": 10, "drawn": 10, "lost": 18,
            "goals_for": 40, "goals_against": 50, "points": 40, "outcome": outcome}


def _fixture(conn: Connection, fid: int, season_id: int, comp: int, stage: str, home: int,
             away: int, day: str, played: bool = True, rnd: int = 1) -> None:
    conn.execute(fixture.insert().values(
        id=fid, season_id=season_id, competition_id=comp, stage=stage, round=rnd, date=day,
        home_club_id=home, away_club_id=away, neutral=0,
        status="played" if played else "scheduled", home_goals=2 if played else None,
        away_goals=1 if played else None))


def _line(conn: Connection, fid: int, pid: int, club_id: int, started: bool, minutes: int,
          goals: int = 0, assists: int = 0, rating: float = 6.5, yellow: int = 0,
          red: int = 0) -> None:
    conn.execute(player_match.insert().values(
        fixture_id=fid, player_id=pid, club_id=club_id, started=int(started), minutes=minutes,
        goals=goals, assists=assists, rating=rating, yellow=yellow, red=red))


def _build(conn: Connection) -> None:
    """Season 1 is over and season 2 has begun (1 July 2027). ENG1: B champions, A relegated.
    ENG2: C champions (promoted), E win the play-offs (promoted)."""
    conn.execute(nation.insert().values(id=1, name="England", code="ENG"))
    conn.execute(season.insert(), [
        {"id": 1, "label": "2026-27", "start_date": "2026-07-01", "end_date": "2027-06-30"},
        {"id": 2, "label": "2027-28", "start_date": NEW_SEASON, "end_date": "2028-06-30"}])
    conn.execute(competition.insert(), [
        {"id": ENG1, "key": "ENG1", "name": "Premier League", "short_name": "PL", "nation_id": 1,
         "type": "league", "tier": 1, "sim_level": "playable"},
        {"id": ENG2, "key": "ENG2", "name": "EFL Championship", "short_name": "EFL",
         "nation_id": 1, "type": "league", "tier": 2, "sim_level": "playable"},
        {"id": FA_CUP, "key": "FA_CUP", "name": "FA Cup", "short_name": "FA", "nation_id": 1,
         "type": "cup", "tier": None, "sim_level": "playable"}])
    conn.execute(club.insert(), [{"id": i, "name": n, "nation_id": 1, "reputation": 50}
                                 for i, n in ((A, "Alton"), (B, "Bexley"), (C, "Carlow"),
                                              (D, "Dunmow"), (E, "Eastry"))])
    for season_id, table in ((1, {ENG1: (A, B), ENG2: (C, D, E)}),
                             (2, {ENG1: (B, C, E), ENG2: (A, D)})):
        conn.execute(club_league_membership.insert(), [
            {"club_id": c, "season_id": season_id, "competition_id": comp}
            for comp, clubs in table.items() for c in clubs])
    conn.execute(league_final.insert(), [
        _final(1, ENG1, B, 1, "champion"), _final(1, ENG1, A, 2, "relegated"),
        _final(1, ENG2, C, 1, "champion"), _final(1, ENG2, D, 2, None),
        _final(1, ENG2, E, 3, "playoff_winner")])
    conn.execute(playoff_tie.insert().values(
        season_id=1, competition_id=ENG2, playoff_key="ENG2_PO", tie="F", round=2, club_a_id=E,
        club_b_id=D, rank_a=3, rank_b=2, winner_club_id=E))
    conn.execute(cup_tie.insert().values(
        season_id=1, competition_id=FA_CUP, round=7, tie="1", club_a_id=B, club_b_id=C,
        winner_club_id=B))
    conn.execute(game_meta.insert(), [{"key": k, "value": json.dumps(v)} for k, v in {
        "world_seed": 7, "game_date": NEW_SEASON, "season_id": 2, "base_calendar": "ENG-2026-27",
        "user_club_id": A, "manager_name": "Test"}.items()])

    # The user's squad: three players he can see develop, a youngster, and a retired veteran.
    _person(conn, P1, "Pat", "2004-03-01", 60)
    _person(conn, P2, "Pip", "1996-03-01", 70)
    _person(conn, P3, "Pop", "2000-03-01", 65)
    _person(conn, OLD, "Oldman", "1990-03-01", 30, retired=NEW_SEASON)
    _person(conn, YOUTH, "Young", "2011-09-01", 40, pa=82)
    for pid in (P1, P2, P3):
        _contract(conn, pid, A)
    _contract(conn, OLD, A, active=False, end=NEW_SEASON)
    _contract(conn, YOUTH, A, kind="youth", start=NEW_SEASON)
    # Others: a retired star and a retired journeyman at B, and a free agent who left the game.
    _person(conn, STAR, "Star", "1989-03-01", 95, retired=NEW_SEASON)
    _person(conn, OTHER, "Other", "1989-03-01", 30, retired=NEW_SEASON)
    _person(conn, FREE, "Free", "1989-03-01", 95, retired=NEW_SEASON)
    _contract(conn, STAR, B, active=False, end=NEW_SEASON)
    _contract(conn, OTHER, B, active=False, end=NEW_SEASON)

    # Their overalls as each season began: P1 up, P2 down, P3 level.
    conn.execute(player_season_overall.insert(), [
        {"season_id": s, "player_id": pid, "overall": o, "recorded_on": f"{2026 + s - 1}-07-01"}
        for s, rows in ((1, {P1: 60, P2: 70, P3: 65}), (2, {P1: 63, P2: 68, P3: 65}))
        for pid, o in rows.items()])


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_database(tmp_path / "save.sqlite")
    with engine.begin() as conn:
        _build(conn)
    yield engine
    engine.dispose()


def test_the_summary_names_every_champion_and_the_moves(engine: Engine, world: World) -> None:
    with engine.connect() as conn:
        review = season_review(conn, world, 1, A)
    assert (review.season, review.next_season) == ("2026-27", "2027-28")
    assert [(h.kind, h.key, h.winner.name) for h in review.honours] == [
        ("league", "ENG1", "Bexley"), ("league", "ENG2", "Carlow"),
        ("playoff", "ENG2_PO", "Eastry"), ("cup", "FA_CUP", "Bexley")]
    assert {h.nation for h in review.honours} == {"ENG"}
    assert [(m.club.name, m.from_league, m.to_league, m.position, m.via_playoffs)
            for m in review.promoted] == [
        ("Carlow", "EFL Championship", "Premier League", 1, False),
        ("Eastry", "EFL Championship", "Premier League", 3, True)]
    assert [(m.club.name, m.from_league, m.to_league, m.position)
            for m in review.relegated] == [("Alton", "Premier League", "EFL Championship", 2)]


def test_the_summary_shows_how_the_squad_developed(engine: Engine, world: World) -> None:
    with engine.connect() as conn:
        review = season_review(conn, world, 1, A)
    assert [(d.name, d.position, d.age, d.before, d.after, d.change)
            for d in review.development] == [
        ("Pat Test", "CM", 23, 60, 63, 3), ("Pip Test", "CM", 31, 70, 68, -2)]  # Pop is level
    assert review.development_recorded and review.development_since is None


def test_a_baseline_taken_part_way_through_the_season_is_said_to_be(engine: Engine,
                                                                    world: World) -> None:
    with engine.begin() as conn:
        conn.execute(update(player_season_overall).where(
            player_season_overall.c.season_id == 1).values(recorded_on="2026-10-14"))
    with engine.connect() as conn:
        review = season_review(conn, world, 1, A)
    assert review.development_recorded and review.development_since == "2026-10-14"
    with engine.begin() as conn:  # and a season with no record at all says that
        conn.execute(delete(player_season_overall).where(player_season_overall.c.season_id == 1))
    with engine.connect() as conn:
        review = season_review(conn, world, 1, A)
    assert not review.development_recorded and review.development == []


def test_the_summary_lists_retirements_and_the_youth_intake(engine: Engine, world: World) -> None:
    with engine.connect() as conn:
        review = season_review(conn, world, 1, A)
        stars = player_overalls(conn, world, [STAR, OLD])
    assert stars[STAR] >= world.defs.lifecycle.retirement.news_from > stars[OLD]
    # The user's own veteran and another club's star; not the journeyman or the free agent.
    assert [(r.name, r.club.name if r.club else None, r.own_player, r.age)
            for r in review.retired] == [
        ("Star Test", "Bexley", False, 38), ("Oldman Test", "Alton", True, 37)]
    (youngster,) = review.youth
    assert (youngster.name, youngster.position, youngster.age) == ("Young Test", "CM", 15)
    assert youngster.potential.low <= youngster.potential.high


def test_the_season_final_carries_the_finish_the_review_and_the_other_news(
        engine: Engine, world: World) -> None:
    messages = [
        "Player development. Improved: Pat Test 60→63 (every attribute up).",
        "Bexley are Premier League champions.", "Eastry win the Championship Play-offs.",
        "Bexley win the FA Cup.", "Carlow promoted to the Premier League.",
        "Alton relegated to the EFL Championship.", "Star Test (Bexley) retires at 38.",
        "Oldman Test retires at 37.", "Youth intake: Young Test (CM, 15) join from the academy.",
        "The 2027-28 season begins.", "Alton are out of the FA Cup, beaten by Bexley in the "
        "Third round.", "New leagues: Eredivisie are played from this season."]
    with engine.connect() as conn:
        final = season_final(conn, world, A, messages)
    assert final is not None
    assert (final.competition, final.position, final.outcome) == ("Premier League", 2, "relegated")
    assert final.review is not None and len(final.review.honours) == 4
    assert final.news == [messages[-2], messages[-1]]  # what no section of the review shows
    assert other_news([]) == []


def test_the_record_of_each_season_starts_for_players_still_playing(engine: Engine,
                                                                    world: World) -> None:
    with engine.begin() as conn:
        record_season_start(conn, world, 2, date(2027, 7, 1))  # P1-P3 already have a season 2
        rows = {r.player_id: r for r in conn.execute(
            select(player_season_overall).where(player_season_overall.c.season_id == 2))}
        fresh = player_overalls(conn, world)
    assert OLD not in fresh and STAR not in fresh and YOUTH in fresh  # the retired are left out
    assert {P1, P2, P3, YOUTH} <= set(rows)
    assert rows[P1].overall == 63 and rows[P1].recorded_on == "2027-07-01"  # first row is kept
    assert rows[YOUTH].overall == fresh[YOUTH] and rows[YOUTH].recorded_on == NEW_SEASON


def test_a_players_seasons_by_competition_with_totals(engine: Engine, world: World) -> None:
    with engine.begin() as conn:
        for fid, comp, stage, home, away, day in (
                (1, ENG1, "league", A, B, "2026-08-10"), (2, ENG1, "league", B, A, "2026-08-17"),
                (3, ENG1, "league", A, B, "2026-08-24"), (4, FA_CUP, "FA_CUP", A, D, "2026-09-05"),
                (5, ENG2, "league", C, D, "2026-12-05"), (6, ENG2, "ENG2_PO", C, D, "2027-05-20"),
                (7, ENG2, "league", A, D, "2027-08-10")):
            _fixture(conn, fid, 1 if fid < 7 else 2, comp, stage, home, away, day)
        _line(conn, 1, P1, A, True, 90, goals=1, assists=1, rating=7.5, yellow=1)
        _line(conn, 2, P1, A, True, 60, rating=6.0)
        _line(conn, 3, P1, A, False, 30, goals=2, rating=8.0, red=1)
        _line(conn, 4, P1, A, True, 90, rating=7.0)
        _line(conn, 5, P1, C, True, 90, rating=6.5)  # on loan at Carlow part-way through
        _line(conn, 6, P1, C, False, 20, goals=1, rating=7.0)
        _line(conn, 7, P1, A, True, 90, assists=1, rating=6.5)
        _line(conn, 1, P2, A, True, 90)  # someone else's matches aren't his
    with engine.connect() as conn:
        seasons = queries.player_seasons(conn, world, P1)
        assert queries.player_seasons(conn, world, P3) == []
        with pytest.raises(KeyError):
            queries.player_seasons(conn, world, 999)

    assert [(s.season_id, s.season) for s in seasons] == [(2, "2027-28"), (1, "2026-27")]
    now, last = seasons
    assert [(ln.competition, ln.club.name if ln.club else None, ln.appearances)
            for ln in now.lines] == [("EFL Championship", "Alton", 1)]
    assert [(ln.competition_key, ln.competition, ln.club.name if ln.club else None)
            for ln in last.lines] == [
        ("ENG1", "Premier League", "Alton"), ("ENG2", "EFL Championship", "Carlow"),
        ("ENG2_PO", "Championship Play-offs", "Carlow"), ("FA_CUP", "FA Cup", "Alton")]
    league = last.lines[0]
    assert (league.appearances, league.starts, league.minutes) == (3, 2, 180)
    assert (league.goals, league.assists, league.yellow, league.red) == (3, 1, 1, 1)
    assert league.average_rating == 7.17  # (7.5 + 6.0 + 8.0) / 3
    total = last.total
    assert total.club is None and total.competition == "All competitions"
    assert (total.appearances, total.starts, total.minutes) == (6, 4, 380)
    assert (total.goals, total.assists, total.yellow, total.red) == (4, 1, 1, 1)
    assert total.average_rating == 7.0  # (7.5 + 6.0 + 8.0 + 7.0 + 6.5 + 7.0) / 6


def test_fixtures_can_be_browsed_by_season(engine: Engine) -> None:
    with engine.begin() as conn:
        _fixture(conn, 1, 1, ENG1, "league", A, B, "2026-08-10")
        _fixture(conn, 2, 1, FA_CUP, "FA_CUP", D, A, "2026-09-05", rnd=0)
        _fixture(conn, 3, 2, ENG2, "league", A, D, "2027-08-10", played=False)
        _fixture(conn, 4, 2, ENG2, "league", C, D, "2027-08-10", played=False)
    with engine.connect() as conn:
        assert [f.id for f in queries.fixtures(conn, club_id=A)] == [3]  # the current season
        assert [f.id for f in queries.fixtures(conn, club_id=A, season_id=1)] == [1, 2]
        assert queries.fixtures(conn, club_id=A, season_id=9) == []


def test_the_league_page_can_tell_a_season_not_yet_started(engine: Engine, world: World) -> None:
    with engine.begin() as conn:
        _fixture(conn, 1, 1, ENG1, "league", A, B, "2026-08-10")
        _fixture(conn, 2, 2, ENG2, "league", A, D, "2027-08-10", played=False)
    with engine.connect() as conn:
        assert [(s.label, s.current, s.finished) for s in queries.seasons(conn)] == [
            ("2027-28", True, False), ("2026-27", False, True)]
        last = queries.table(conn, world, "ENG1", 1)
        assert last.started and last.final and last.name == "Premier League"
        assert last.first_match == "2026-08-10"
        now = queries.table(conn, world, "ENG1")  # the new season, before its first match
        assert not now.started and not now.final and now.season == "2027-28"
        assert now.first_match is None  # ENG1 has no fixtures in the new season in this save
        assert not queries.table(conn, world, "ENG2").started
        assert queries.table(conn, world, "ENG2").first_match == "2027-08-10"
    with engine.begin() as conn:  # its first match is played
        conn.execute(update(fixture).where(fixture.c.id == 2).values(
            status="played", home_goals=0, away_goals=0))
    with engine.connect() as conn:
        assert queries.table(conn, world, "ENG2").started
