"""UEFA's country ranking from the real seasons (W7 A2): the five-season sums reproduce UEFA's
2025 and 2026 rankings, a season's access list uses the ranking from two seasons back, the
European Performance Spots go to the best two of the season before, and the league-phase place
bonus follows UEFA's 2024-27 table."""

from footsim.world.context import get_world
from footsim.world.europe.ranking import (
    access_ranking,
    performance_spots,
    ranking,
    season_id_of,
    season_label_of,
    uefa_nations,
)

# UEFA's 2025 ranking (2020-21 to 2024-25), Russia left out.
UEFA_2025 = ["ENG", "ITA", "ESP", "GER", "FRA", "NED", "POR", "BEL", "CZE", "TUR", "NOR", "GRE",
             "AUT", "SCO", "POL", "DEN", "SUI", "ISR", "CYP", "SWE", "CRO", "SRB", "UKR", "HUN",
             "ROU", "SVK", "SVN", "BUL", "AZE", "IRL", "MDA", "ISL", "BIH", "ARM", "LVA", "KOS",
             "FIN", "KAZ", "FRO", "MLT", "NIR", "LTU", "LIE", "EST", "ALB", "MNE", "LUX", "WAL",
             "GEO", "MKD", "BLR", "AND", "GIB", "SMR"]


def test_the_real_rankings() -> None:
    world = get_world()
    assert len(uefa_nations(world)) == 54 and "RUS" not in uefa_nations(world)
    r2025 = ranking(None, world, -1)  # through 2024-25: season 0 is 2025-26
    assert [r.nation for r in r2025] == UEFA_2025
    assert round(r2025[0].total, 3) == 115.196 and round(r2025[-1].total, 3) == 2.498
    r2026 = ranking(None, world, 0)
    assert [r.nation for r in r2026[:6]] == ["ENG", "ITA", "ESP", "GER", "FRA", "POR"]
    assert round(r2026[0].total, 3) == 119.519 and r2026[-1].nation == "SMR"
    # Season 1 (2026-27) uses the 2025 ranking; season 2 the 2026 one.
    assert [r.nation for r in access_ranking(None, world, 1)] == UEFA_2025
    assert [r.nation for r in access_ranking(None, world, 2)] == [r.nation for r in r2026]


def test_the_performance_spots_and_season_labels() -> None:
    world = get_world()
    assert performance_spots(None, world, 1) == ["ENG", "ESP"]  # from 2025-26, as in real life
    assert season_id_of("2026-27", "2026-27") == 1 and season_id_of("2020-21", "2026-27") == -5
    assert season_label_of(0, "2026-27") == "2025-26" and season_label_of(3, "2026-27") == "2028-29"


def test_the_league_phase_place_bonus() -> None:
    rules = get_world().defs.europe.coefficient
    ucl, uecl = rules.ranking_bonus["UCL"], rules.ranking_bonus["UECL"]
    assert [ucl.points(p) for p in (1, 8, 9, 24, 25, 36)] == [6.0, 4.25, 4.0, 0.25, 0.0, 0.0]
    assert [uecl.points(p) for p in (1, 9, 24)] == [4.0, 2.0, 0.125]
    assert rules.league_phase_bonus["UCL"] + ucl.points(1) == 12.0  # UEFA's 12 for 1st
