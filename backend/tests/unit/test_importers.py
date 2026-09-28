"""Importer tests on synthetic rows shaped like the EA export (no real data needed)."""

import csv
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from footsim.core.paths import data_dir
from footsim.defs.loader import GameDefinitions, load_definitions
from footsim.domain.attributes import ATTRIBUTES
from footsim.importers.build_world import build_world
from footsim.importers.csv_source import SourceFormatError, read_players
from footsim.importers.derive import complete_attributes, traits_for
from footsim.importers.generate import draw_potential, generated_contract_end, weekly_wage_cents
from footsim.importers.profile import ImportProfile, load_profile
from footsim.importers.records import SourcePlayer, TmPlayer
from footsim.importers.resolve import match_players, normalize

PROFILE_PATH = data_dir() / "import_profiles" / "ea_fc_ratings_v1.yaml"


@pytest.fixture(scope="module")
def profile() -> ImportProfile:
    return load_profile(PROFILE_PATH)


@pytest.fixture(scope="module")
def defs() -> GameDefinitions:
    return load_definitions()


def ea_row(profile: ImportProfile, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {column: 60 for column in profile.attributes.values()}
    row.update({
        "player_id": "1", "common_name": "", "first_name": "Test", "last_name": "Player",
        "overall_rating": 70, "position": "CM", "alternate_positions": "", "club": "Test FC",
        "league": "Premier League", "nationality": "England", "gender": "Men's Football",
        "preferred_foot": "Right", "skill_moves": 3, "weak_foot": 3, "height_cm": "",
        "weight_kg": "", "birthdate": "2000-01-01", "playstyles": "",
    })
    row.update(overrides)
    return row


def write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def source_player(**overrides: Any) -> SourcePlayer:
    values: dict[str, Any] = {
        "source": "test", "source_id": "1", "first_name": "Test", "last_name": "Player",
        "known_as": None, "birth_date": date(2000, 1, 1), "nationality": "England",
        "club": "Test FC", "league": "Premier League", "position": "CM", "alt_positions": [],
        "preferred_foot": "right", "weak_foot": 3, "skill_moves": 3, "height_cm": None,
        "weight_kg": None, "source_overall": 70, "playstyles": [],
    }
    values.update(overrides)
    return SourcePlayer(**values)


def tm_player(tm_id: int, name: str, birth: date, club: str = "Test FC") -> TmPlayer:
    first, _, last = name.partition(" ")
    return TmPlayer(tm_id=tm_id, name=name, first_name=first, last_name=last, birth_date=birth,
                    citizenship="England", height_cm=180, foot="right", position=None,
                    sub_position=None, contract_expiry=None, market_value_eur=None,
                    club_name=club, city_of_birth=None)


def test_repository_profile_covers_every_attribute(profile: ImportProfile) -> None:
    assert set(profile.attributes) | set(profile.derived) == set(ATTRIBUTES)


def test_profile_must_cover_every_attribute(profile: ImportProfile) -> None:
    data = profile.model_dump(by_alias=True)
    del data["derived"]["flair"]
    with pytest.raises(ValidationError, match="neither imported nor derived"):
        ImportProfile.model_validate(data)


def test_read_players_filters_and_maps_positions(tmp_path: Path, profile: ImportProfile) -> None:
    path = write_csv(tmp_path / "p.csv", [
        ea_row(profile, player_id="1", position="CDM", alternate_positions="CM CDM CAM",
               playstyles="Anticipate+, Intercept"),
        ea_row(profile, player_id="2", gender="Women's Football"),
    ])
    (player,) = read_players(path, profile)
    assert player.position == "DM"
    assert player.alt_positions == ["CM", "AM"]
    assert player.playstyles == ["Anticipate+", "Intercept"]


def test_read_players_rejects_unknown_position(tmp_path: Path, profile: ImportProfile) -> None:
    path = write_csv(tmp_path / "p.csv", [ea_row(profile, position="SW")])
    with pytest.raises(SourceFormatError, match="unmapped position"):
        read_players(path, profile)


def test_complete_attributes(tmp_path: Path, profile: ImportProfile) -> None:
    path = write_csv(tmp_path / "p.csv", [ea_row(profile)])
    (player,) = read_players(path, profile)
    attrs = complete_attributes(player, profile, seed=1)
    assert set(attrs) == set(ATTRIBUTES)
    assert all(1 <= v <= 99 for v in attrs.values())
    assert attrs == complete_attributes(player, profile, seed=1)
    # Outfield players get their (low) goalkeeping level, not a derived keeper rating.
    assert attrs["gk_one_on_ones"] == 60


def test_playstyle_plus_raises_derived_attribute(tmp_path: Path, profile: ImportProfile) -> None:
    rows = [ea_row(profile, player_id="7"), ea_row(profile, player_id="7",
                                                    playstyles="Anticipate+")]
    plain = read_players(write_csv(tmp_path / "a.csv", rows[:1]), profile)[0]
    styled = read_players(write_csv(tmp_path / "b.csv", rows[1:]), profile)[0]
    gain = (complete_attributes(styled, profile, 1)["anticipation"]
            - complete_attributes(plain, profile, 1)["anticipation"])
    assert gain == pytest.approx(6 * profile.plus_multiplier, abs=1)
    assert traits_for(styled, profile) == ["reads_play"]


def test_normalize_folds_accents() -> None:
    assert normalize("Martin Ødegaard") == "martin odegaard"
    assert normalize("Kylian Mbappé") == "kylian mbappe"


def test_twins_are_not_confused() -> None:
    born = date(2001, 6, 17)
    result = match_players(
        [source_player(source_id="a", first_name="Jurriën", last_name="Timber", birth_date=born),
         source_player(source_id="b", first_name="Quinten", last_name="Timber", birth_date=born)],
        [tm_player(1, "Jurrien Timber", born), tm_player(2, "Quinten Timber", born)],
    )
    assert result.matches["a"].tm_id == 1
    assert result.matches["b"].tm_id == 2


def test_twin_missing_from_other_source_stays_unmatched() -> None:
    born = date(1996, 9, 30)
    result = match_players(
        [source_player(source_id="nico", first_name="Nico", last_name="Elvedi", birth_date=born),
         source_player(source_id="jan", first_name="Jan", last_name="Elvedi", birth_date=born)],
        [tm_player(1, "Nico Elvedi", born)],
    )
    assert result.matches["nico"].tm_id == 1
    assert "jan" not in result.matches


def test_birth_dates_a_day_apart_still_match() -> None:
    result = match_players(
        [source_player(first_name="Omari", last_name="Hutchinson", birth_date=date(2003, 10, 29))],
        [tm_player(9, "Omari Hutchinson", date(2003, 10, 30))],
    )
    assert result.matches["1"].tm_id == 9


def test_different_player_same_birthday_not_matched() -> None:
    result = match_players(
        [source_player(first_name="Alan", last_name="Smith")],
        [tm_player(1, "Bruno Costa", date(2000, 1, 1))],
    )
    assert result.unmatched == ["1"]


def test_potential_and_contracts(defs: GameDefinitions) -> None:
    rng = np.random.default_rng(0)
    rules = defs.world_build
    young = [draw_potential(65, 18, rules.potential, rng) for _ in range(200)]
    assert min(young) >= 65 and np.mean(young) > 72
    assert draw_potential(80, 31, rules.potential, rng) == 80
    end = generated_contract_end(34, date(2026, 7, 1), rules.contracts, rng)
    assert end in (date(2027, 6, 30), date(2028, 6, 30))
    wage = weekly_wage_cents(40, defs.wage_levels.default, 400, rng)
    assert wage >= 400 * 100


def test_build_world_end_to_end(tmp_path: Path, profile: ImportProfile,
                                defs: GameDefinitions) -> None:
    rows = [
        ea_row(profile, player_id=str(i), club=f"Club {i % 2}", position=pos,
               alternate_positions="LB" if pos == "CB" else "")
        for i, pos in enumerate(["GK", "CB", "ST", "CM"])
    ]
    tm = [tm_player(50, "Test Player", date(2000, 1, 1), club="Club 0")]
    rows[0]["first_name"], rows[0]["last_name"] = "Test", "Player"
    for row in rows[1:]:
        row["first_name"], row["birthdate"] = f"Other{row['player_id']}", "1999-05-05"
    out = tmp_path / "world.sqlite"
    report = build_world(ea_csv=write_csv(tmp_path / "p.csv", rows), profile=profile, defs=defs,
                         out_path=out, calendar_key="ENG-2026-27", seed=7, tm_players=tm,
                         strict=False)
    assert report.players == 4 and report.clubs == 2 and report.tm_matched == 1
    assert any("ENG1 expects 20 clubs" in w for w in report.warnings)

    db = sqlite3.connect(out)
    assert db.execute("SELECT count(*) FROM player_attr").fetchone() == (4,)
    assert db.execute("SELECT count(*) FROM club_league_membership").fetchone() == (2,)
    cb_positions = db.execute(
        "SELECT position, familiarity FROM player_position WHERE player_id = 2"
    ).fetchall()
    assert ("CB", 20) in cb_positions and ("LB", 15) in cb_positions
    assert db.execute(
        "SELECT source_id FROM external_id WHERE source = 'transfermarkt'"
    ).fetchall() == [("50",)]
    assert db.execute("SELECT value FROM game_meta WHERE key = 'world_seed'").fetchone() == ("7",)


def test_elite_potential_is_rare(defs: GameDefinitions) -> None:
    rng = np.random.default_rng(3)
    rules = defs.world_build.potential
    draws = np.array([draw_potential(72, 18, rules, rng) for _ in range(2000)])
    assert np.mean(draws) > 80  # a good 18-year-old usually improves a lot...
    assert np.mean(draws >= 90) < 0.05  # ...but rarely becomes world class
