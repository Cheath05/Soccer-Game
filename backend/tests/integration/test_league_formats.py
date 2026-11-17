"""The league formats of the Americas (W9a B1), played for a whole season on the base world's
own clubs: conferences with cross-conference matches and a play-off with a Wild Card, best-of-three
series and a final at the better seed (MLS's shape); Apertura and Clausura, each with its own
two-legged Liguilla where a level tie goes to the better seed (Liga MX's); and zones with
interzonal rivals, two tournaments and an annual table with its own title (Argentina's). The
leagues are defined here, beside the world's own, so the test checks the formats, not the
Americas' data files. Needs the built world."""

import shutil
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Connection, select, text

from footsim.core.paths import data_dir
from footsim.defs.calendar import SeasonCalendarDef
from footsim.defs.competitions import LeagueDef
from footsim.defs.finance import LeagueIncome
from footsim.persistence.database import open_database
from footsim.persistence.migrations import migrate
from footsim.persistence.schema import competition, fixture, league_final, league_title, playoff_tie
from footsim.world.career import advance, initialize_career
from footsim.world.context import World, get_world

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"
pytestmark = pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")

EAST = ["Atlanta United", "Charlotte FC", "Chicago Fire FC", "Columbus Crew", "D.C. United",
        "FC Cincinnati", "Inter Miami CF", "CF Montréal", "Nashville SC", "New England",
        "New York City FC", "Red Bulls", "Orlando City", "Philadelphia", "Toronto FC"]
WEST = ["Austin FC", "Colorado Rapids", "FC Dallas", "Houston Dynamo", "LA Galaxy", "LAFC",
        "Minnesota United", "Portland Timbers", "Real Salt Lake", "SJ Earthquakes",
        "San Diego FC", "Sounders FC", "Sporting KC", "St. Louis CITY SC", "Whitecaps FC"]
LIGA_MX = ["Atlante FC", "Atlas FC", "Atltico de SL", "CF Cruz Azul", "Club América",
           "Club Guadalajara", "Club Len", "Club Necaxa", "Club Pachuca", "Club Puebla",
           "Club Tigres", "Club Tijuana", "FC Jurez", "Monterrey", "Pumas", "Quertaro FC",
           "Santos Laguna", "Toluca FC"]
ZONE_A = ["Aldosivi", "Argentinos Jrs.", "Asociación Atlética Estudiantes", "Atlético Tucumán",
          "Banfield", "Barracas Central", "Belgrano", "Boca Juniors", "Central Córdoba",
          "Club Atlético Gimnasia y Esgrima", "Defensa", "Dep. Riestra", "Estudiantes",
          "Gimnasia", "Huracán"]
ZONE_B = ["Independiente", "Ind. Rivadavia", "Instituto", "Lanús", "Newell's", "Platense",
          "River Plate", "Racing Club", "Rosario Central", "San Lorenzo", "Sarmiento",
          "Talleres", "Tigre", "Unión", "Vélez Sarsfield"]
WINDOWS = [{"start": "2026-09-21", "end": "2026-10-06"},
           {"start": "2026-11-09", "end": "2026-11-17"},
           {"start": "2027-03-22", "end": "2027-03-30"}]


def _ref(group: str | None, rank: int) -> dict[str, Any]:
    return {"rank": rank, **({"group": group} if group else {})}


def _won(*ties: str, pick: str = "only") -> dict[str, Any]:
    return {"winner_of": list(ties), **({"pick": pick} if pick != "only" else {})}


def _mls() -> dict[str, Any]:
    rounds: list[dict[str, Any]] = [
        {"name": "Wild Card", "extra_time": False, "ties": [
            {"id": f"WC{g}", "a": _ref(g, 8), "b": _ref(g, 9)} for g in "EW"]},
        {"name": "Round One", "games": 3, "extra_time": False, "ties": [
            t for g in "EW" for t in (
                {"id": f"{g}1", "a": _ref(g, 1), "b": _won(f"WC{g}")},
                {"id": f"{g}2", "a": _ref(g, 2), "b": _ref(g, 7)},
                {"id": f"{g}3", "a": _ref(g, 3), "b": _ref(g, 6)},
                {"id": f"{g}4", "a": _ref(g, 4), "b": _ref(g, 5)})]},
        {"name": "Conference Semifinals", "ties": [
            t for g in "EW" for t in (
                {"id": f"{g}S1", "a": _won(f"{g}1"), "b": _won(f"{g}4")},
                {"id": f"{g}S2", "a": _won(f"{g}2"), "b": _won(f"{g}3")})]},
        {"name": "Conference Finals", "ties": [
            {"id": f"{g}F", "a": _won(f"{g}S1"), "b": _won(f"{g}S2")} for g in "EW"]},
        {"name": "MLS Cup", "ties": [{"id": "F", "a": _won("EF"), "b": _won("WF")}]},
    ]
    return {"key": "USA1", "name": "Major League Soccer", "short_name": "MLS", "nation": "USA",
            "tier": 1, "clubs": 30, "sim_level": "simulated", "calendar": "TST-USA",
            "source_leagues": ["MLS"],
            "format": {"type": "groups", "legs": 2, "cross_rounds": 6},
            "groups": [{"key": "E", "name": "Eastern Conference", "clubs": EAST},
                       {"key": "W", "name": "Western Conference", "clubs": WEST}],
            "tiebreakers": ["points", "wins", "goal_difference", "goals_for", "h2h_points",
                            "drawing_of_lots"],
            "table_title": "Supporters' Shield",
            "playoffs": [{"key": "USA1_PO", "name": "MLS Cup", "title": True,
                          "rounds": rounds}]}


def _liguilla(phase: str) -> dict[str, Any]:
    level = {"legs": 2, "extra_time": False, "penalties": False, "higher_seed_on_level": True}
    return {"key": f"MEX1_{phase}", "name": f"Liguilla ({phase})", "title": True, "phase": phase,
            "rounds": [
                {"name": "Quarter-finals", **level, "ties": [
                    {"id": f"Q{k}", "a": _ref(None, k), "b": _ref(None, 9 - k)}
                    for k in range(1, 5)]},
                {"name": "Semi-finals", **level, "ties": [
                    {"id": "S1", "a": _won("Q1", "Q2", "Q3", "Q4", pick="highest_ranked"),
                     "b": _won("Q1", "Q2", "Q3", "Q4", pick="lowest_ranked")},
                    {"id": "S2", "a": _won("Q1", "Q2", "Q3", "Q4", pick="second_highest"),
                     "b": _won("Q1", "Q2", "Q3", "Q4", pick="second_lowest")}]},
                {"name": "Final", "legs": 2, "ties": [
                    {"id": "F", "a": _won("S1"), "b": _won("S2")}]}]}


def _mex() -> dict[str, Any]:
    return {"key": "MEX1", "name": "Liga MX", "short_name": "Liga MX", "nation": "MEX",
            "tier": 1, "clubs": 18, "sim_level": "simulated", "calendar": "TST-MEX",
            "source_leagues": ["Liga BBVA MX"], "format": {"type": "round_robin", "legs": 1},
            "phases": [{"key": "AP", "name": "Apertura"}, {"key": "CL", "name": "Clausura"}],
            "tiebreakers": ["points", "goal_difference", "goals_for", "h2h_points",
                            "drawing_of_lots"],
            "playoffs": [_liguilla("AP"), _liguilla("CL")]}


def _arg_playoff(phase: str) -> dict[str, Any]:
    knock = {"extra_time": False}
    return {"key": f"ARG1_{phase}", "name": f"Knockout ({phase})", "title": True, "phase": phase,
            "rounds": [
                {"name": "Round of 16", **knock, "ties": [
                    {"id": f"R{k}", "a": _ref("A", k), "b": _ref("B", 9 - k)}
                    for k in range(1, 9)]},
                {"name": "Quarter-finals", **knock, "ties": [
                    {"id": f"Q{k}", "a": _won(f"R{k}"), "b": _won(f"R{9 - k}")}
                    for k in range(1, 5)]},
                {"name": "Semi-finals", **knock, "ties": [
                    {"id": "S1", "a": _won("Q1"), "b": _won("Q4")},
                    {"id": "S2", "a": _won("Q2"), "b": _won("Q3")}]},
                {"name": "Final", "host": "neutral", "ties": [
                    {"id": "F", "a": _won("S1"), "b": _won("S2")}]}]}


def _arg() -> dict[str, Any]:
    return {"key": "ARG1", "name": "Liga Profesional", "short_name": "LPF", "nation": "ARG",
            "tier": 1, "clubs": 30, "sim_level": "simulated", "calendar": "TST-ARG",
            "source_leagues": ["LPF"],
            "format": {"type": "groups", "legs": 1, "cross_rounds": 2,
                       "rivals": [[a, b] for a, b in zip(ZONE_A, ZONE_B, strict=True)]},
            "groups": [{"key": "A", "name": "Zone A", "clubs": ZONE_A},
                       {"key": "B", "name": "Zone B", "clubs": ZONE_B}],
            "phases": [{"key": "AP", "name": "Apertura"}, {"key": "CL", "name": "Clausura"}],
            "tiebreakers": ["points", "goal_difference", "goals_for", "drawing_of_lots"],
            "table_title": "Campeón de Liga",
            "playoffs": [_arg_playoff("AP"), _arg_playoff("CL")]}


def _calendar(key: str, nation: str, competitions: dict[str, Any],
              blackout: list[dict[str, str]] | None = None) -> SeasonCalendarDef:
    return SeasonCalendarDef.model_validate({
        "key": key, "season": "2026-27", "nation": nation, "season_start": "2026-07-01",
        "season_end": "2027-06-30", "competitions": competitions,
        "international_windows": WINDOWS, "blackout": blackout or []})


@pytest.fixture(scope="module")
def world() -> World:
    base = get_world()
    leagues = {d["key"]: LeagueDef.model_validate(d) for d in (_mls(), _mex(), _arg())}
    calendars = {
        **base.defs.calendars,
        "TST-USA": _calendar("TST-USA", "USA", {"USA1": {
            "start": "2026-07-18", "end": "2027-04-25", "playoffs_end": "2027-05-29"}},
            [{"start": "2026-12-14", "end": "2027-02-05"}]),
        "TST-MEX": _calendar("TST-MEX", "MEX", {
            "MEX1:AP": {"start": "2026-07-10", "end": "2026-11-08", "playoffs_end": "2026-12-13"},
            "MEX1:CL": {"start": "2027-01-08", "end": "2027-04-25", "playoffs_end": "2027-05-30"},
        }),
        "TST-ARG": _calendar("TST-ARG", "ARG", {
            "ARG1:AP": {"start": "2026-07-24", "end": "2026-11-22", "playoffs_end": "2026-12-20"},
            "ARG1:CL": {"start": "2027-01-29", "end": "2027-05-16", "playoffs_end": "2027-06-20"},
        })}
    income = {**base.defs.finance.league_income,
              **{k: LeagueIncome(base=5_000_000, merit=3_000_000) for k in leagues}}
    defs = replace(base.defs, leagues={**base.defs.leagues, **leagues}, calendars=calendars,
                   finance=base.defs.finance.model_copy(update={"league_income": income}))
    return World(defs=defs, model=base.model, picker=base.picker, quick=base.quick)


@pytest.fixture(scope="module")
def season(world: World, tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("formats") / "season.sqlite"
    shutil.copy(BASE_WORLD, path)
    engine = open_database(path)
    migrate(engine)
    with engine.begin() as conn:
        initialize_career(conn, world, None, None, seed=7)
    with engine.begin() as conn:
        result = advance(conn, world, max_days=400)
    assert result.stop == "season_end"
    engine.dispose()
    return path


def _conn(path: Path) -> Connection:
    return open_database(path).connect()


def _ids(conn: Connection) -> dict[str, int]:
    names = {r.name: r.id for r in conn.execute(text("SELECT id, name FROM club"))}
    return names


def _league(conn: Connection, key: str) -> int:
    return int(conn.execute(select(competition.c.id).where(competition.c.key == key)).scalar_one())


def _games(conn: Connection, comp: int, stage: str = "league") -> list[Any]:
    return list(conn.execute(select(fixture).where(
        fixture.c.season_id == 1, fixture.c.competition_id == comp,
        fixture.c.stage == stage).order_by(fixture.c.date, fixture.c.id)))


def _titles(conn: Connection, comp: int) -> dict[str, Any]:
    return {r.title: r for r in conn.execute(select(league_title).where(
        league_title.c.season_id == 1, league_title.c.competition_id == comp))}


def test_conferences_and_the_mls_cup_playoffs(season: Path) -> None:
    with _conn(season) as conn:
        ids = _ids(conn)
        comp = _league(conn, "USA1")
        east, west = {ids[n] for n in EAST}, {ids[n] for n in WEST}
        games = _games(conn, comp)
        assert all(g.status == "played" for g in games)
        meets: Counter[tuple[int, int]] = Counter()
        home: Counter[int] = Counter()
        for g in games:
            meets[tuple(sorted((g.home_club_id, g.away_club_id)))] += 1  # type: ignore[index]
            home[g.home_club_id] += 1
        for club in east | west:
            mine = {pair: n for pair, n in meets.items() if club in pair}
            own = east if club in east else west
            assert sum(mine.values()) == 34
            assert all(n == 2 for pair, n in mine.items() if set(pair) <= own)
            assert sum(1 for pair in mine if not set(pair) <= own) == 6
            assert all(n == 1 for pair, n in mine.items() if not set(pair) <= own)
            assert 15 <= home[club] <= 19
        # No club plays twice on one day.
        for day, clubs in _by_day(games).items():
            assert len(clubs) == len(set(clubs)), day

        ties = {t.tie: t for t in conn.execute(select(playoff_tie).where(
            playoff_tie.c.season_id == 1, playoff_tie.c.playoff_key == "USA1_PO"))}
        assert len(ties) == 2 + 8 + 4 + 2 + 1
        assert all(t.winner_club_id for t in ties.values())
        finals = {r.club_id: r for r in conn.execute(select(league_final).where(
            league_final.c.season_id == 1, league_final.c.competition_id == comp))}
        # Seeds within each conference: 8 v 9 in the Wild Card, 2 v 7 in Round One.
        for g, members in (("E", east), ("W", west)):
            order = sorted(members, key=lambda c: finals[c].position)
            assert {ties[f"WC{g}"].club_a_id, ties[f"WC{g}"].club_b_id} == set(order[7:9])
            assert (ties[f"{g}2"].club_a_id, ties[f"{g}2"].club_b_id) == (order[1], order[6])
            assert ties[f"{g}1"].club_b_id == ties[f"WC{g}"].winner_club_id
            assert not set(order[9:]) & {c for t in ties.values()
                                         for c in (t.club_a_id, t.club_b_id)}
        # Round One: best of three, the better seed at home in games 1 and 3, decided on the day.
        series = [f for f in _games(conn, comp, "USA1_PO") if f.round == 1]
        by_tie: dict[str, list[Any]] = defaultdict(list)
        for f in series:
            by_tie[f.tie.split(":")[0]].append(f)
        assert sorted(by_tie) == sorted(f"{g}{k}" for g in "EW" for k in range(1, 5))
        assert {len(v) for v in by_tie.values()} <= {2, 3}
        for tie_id, played in by_tie.items():
            tie = ties[tie_id]
            wins: Counter[int] = Counter()
            for f in sorted(played, key=lambda f: f.leg):
                assert f.home_club_id == (tie.club_a_id if f.leg % 2 else tie.club_b_id)
                assert not f.extra_time
                level = f.home_goals == f.away_goals
                assert not level or f.home_pens is not None
                won_home = (f.home_goals > f.away_goals if not level
                            else f.home_pens > f.away_pens)
                wins[f.home_club_id if won_home else f.away_club_id] += 1
            assert wins[tie.winner_club_id] == 2 and sum(wins.values()) == len(played)
        # MLS Cup at the finalist higher in the Supporters' Shield table; the titles.
        final = _games(conn, comp, "USA1_PO")[-1]
        assert final.round == 4
        assert finals[final.home_club_id].position < finals[final.away_club_id].position
        titles = _titles(conn, comp)
        top = min(finals, key=lambda c: finals[c].position)
        assert titles["Supporters' Shield"].club_id == top
        assert titles["Supporters' Shield"].kind == "award"
        assert titles["MLS Cup"].club_id == ties["F"].winner_club_id
        assert finals[ties["F"].winner_club_id].outcome == "champion"
        assert finals[top].outcome in ("table_title", "champion")


def _by_day(games: list[Any]) -> dict[str, list[int]]:
    days: dict[str, list[int]] = defaultdict(list)
    for g in games:
        days[g.date] += [g.home_club_id, g.away_club_id]
    return days


def test_apertura_and_clausura_with_their_liguillas(season: Path) -> None:
    with _conn(season) as conn:
        comp = _league(conn, "MEX1")
        games = _games(conn, comp)
        assert {g.round for g in games} == set(range(1, 35))
        first = [g for g in games if g.round <= 17]
        second = [g for g in games if g.round > 17]
        pairs = [(g.home_club_id, g.away_club_id) for g in first]
        assert len({frozenset(p) for p in pairs}) == 153  # every pair once
        assert {(g.away_club_id, g.home_club_id) for g in second} == set(pairs)  # venues swapped
        titles = _titles(conn, comp)
        assert set(titles) == {"Liga MX Apertura", "Liga MX Clausura"}
        assert all(t.kind == "champion" for t in titles.values())
        apertura = _games(conn, comp, "MEX1_AP")
        assert max(g.date for g in apertura) < min(g.date for g in second)
        assert max(g.date for g in first) < min(g.date for g in apertura)
        # The quarter-finals: 1 v 8 ... 4 v 5 of the Apertura's own table, two legs; a level
        # aggregate goes to the better seed, with no extra time or penalties.
        for key in ("MEX1_AP", "MEX1_CL"):
            ties = list(conn.execute(select(playoff_tie).where(
                playoff_tie.c.season_id == 1, playoff_tie.c.playoff_key == key)))
            quarters = [t for t in ties if t.round == 0]
            assert sorted((t.rank_a, t.rank_b) for t in quarters) == [(1, 8), (2, 7), (3, 6),
                                                                      (4, 5)]
            semis = sorted((t for t in ties if t.round == 1), key=lambda t: t.tie)
            through = sorted(t.rank_a if t.winner_club_id == t.club_a_id else t.rank_b
                             for t in quarters)
            assert (semis[0].rank_a, semis[0].rank_b) == (through[0], through[3])
            assert (semis[1].rank_a, semis[1].rank_b) == (through[1], through[2])
            for t in ties:
                if t.round == 2:
                    continue
                legs = [g for g in _games(conn, comp, key) if g.tie == t.tie
                        and g.round == t.round]
                assert len(legs) == 2 and not any(g.extra_time or g.home_pens for g in legs)
                goals: Counter[int] = Counter()
                for g in legs:
                    goals[g.home_club_id] += g.home_goals
                    goals[g.away_club_id] += g.away_goals
                if goals[t.club_a_id] == goals[t.club_b_id]:
                    assert t.winner_club_id == t.club_a_id  # the better seed
            assert ties and all(t.winner_club_id for t in ties)
        finals = list(conn.execute(select(league_final).where(
            league_final.c.season_id == 1, league_final.c.competition_id == comp)))
        assert len(finals) == 18 and all(f.played == 34 for f in finals)
        assert not any(f.outcome for f in finals)  # the annual table crowns no one


def test_zones_rivals_and_the_annual_title(season: Path) -> None:
    with _conn(season) as conn:
        ids = _ids(conn)
        comp = _league(conn, "ARG1")
        zone_a = {ids[n] for n in ZONE_A}
        rival = {ids[a]: ids[b] for a, b in zip(ZONE_A, ZONE_B, strict=True)}
        rival |= {b: a for a, b in rival.items()}
        games = _games(conn, comp)
        rounds = max(g.round for g in games)
        assert rounds == 34
        drawn: dict[int, list[int]] = defaultdict(list)
        for phase in (range(1, 18), range(18, 35)):
            mine: Counter[int] = Counter()
            for g in games:
                if g.round in phase:
                    mine[g.home_club_id] += 1
                    mine[g.away_club_id] += 1
                    a, b = g.home_club_id, g.away_club_id
                    if (a in zone_a) != (b in zone_a) and rival[a] != b:
                        drawn[a].append(b)
                        drawn[b].append(a)
            assert set(mine.values()) == {16}  # 14 in the zone, the rival, one drawn
            assert sum(1 for g in games if g.round in phase
                       and rival.get(g.home_club_id) == g.away_club_id) == 15
        assert all(len(v) == 2 and v[0] != v[1] for v in drawn.values())
        titles = _titles(conn, comp)
        assert set(titles) == {"LPF Apertura", "LPF Clausura", "Campeón de Liga"}
        finals = {r.club_id: r for r in conn.execute(select(league_final).where(
            league_final.c.season_id == 1, league_final.c.competition_id == comp))}
        assert titles["Campeón de Liga"].club_id == min(finals, key=lambda c: finals[c].position)
        r16 = list(conn.execute(select(playoff_tie).where(
            playoff_tie.c.season_id == 1, playoff_tie.c.playoff_key == "ARG1_AP",
            playoff_tie.c.round == 0)))
        assert len(r16) == 8
        assert all((t.club_a_id in zone_a) != (t.club_b_id in zone_a) for t in r16)


def test_the_season_rolls_over(season: Path) -> None:
    with _conn(season) as conn:
        for key, size in (("USA1", 30), ("MEX1", 18), ("ARG1", 30)):
            count = conn.execute(text(
                "SELECT COUNT(*) FROM club_league_membership m JOIN competition c "
                "ON c.id = m.competition_id WHERE c.key = :k AND m.season_id = 2"),
                {"k": key}).scalar_one()
            assert count == size, key
            assert conn.execute(select(fixture.c.id).where(
                fixture.c.season_id == 2, fixture.c.competition_id == _league(conn, key))
            ).first() is not None


def test_the_tables_and_play_offs_the_screens_read(season: Path, world: World) -> None:
    from footsim.api import queries

    with _conn(season) as conn:
        mls = queries.table(conn, world, "USA1", 1)
        assert len(mls.rows) == 30 and [g.key for g in mls.groups] == ["E", "W"]
        assert all(len(g.rows) == 15 for g in mls.groups)
        assert [r.position for r in mls.groups[0].rows] == list(range(1, 16))
        assert {r.zone for g in mls.groups for r in g.rows[:9]} == {"playoff"}
        assert {r.zone for g in mls.groups for r in g.rows[9:]} == {None}
        assert {t.title for t in mls.titles} == {"Supporters' Shield", "MLS Cup"}
        assert mls.phases == [] and mls.phase is None
        playoff = queries.league_playoffs(conn, world, "USA1", 1)[0]
        assert [len(r.ties) for r in playoff.rounds] == [2, 8, 4, 2, 1]
        assert {len(t.fixtures) for t in playoff.rounds[1].ties} <= {2, 3}
        assert playoff.winner is not None and playoff.title

        mex = queries.table(conn, world, "MEX1", 1)
        assert mex.phase == "CL"  # a finished season shows its last phase
        assert [p.key for p in mex.phases] == ["AP", "CL", "season"]
        assert all(r.played == 17 for r in mex.rows)
        assert sum(r.zone == "playoff" for r in mex.rows) == 8
        whole = queries.table(conn, world, "MEX1", 1, "season")
        assert whole.phase == "season" and all(r.played == 34 for r in whole.rows)
        assert {p.phase for p in queries.league_playoffs(conn, world, "MEX1", 1)} == {"AP", "CL"}

        arg = queries.table(conn, world, "ARG1", 1, "AP")
        assert [len(g.rows) for g in arg.groups] == [15, 15]
        assert sum(r.zone == "playoff" for g in arg.groups for r in g.rows) == 16
