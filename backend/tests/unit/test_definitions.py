import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from footsim.core.paths import config_dir
from footsim.defs.common import Point
from footsim.defs.competitions import EntrantRef, PlayoffDef
from footsim.defs.formations import FormationDef
from footsim.defs.loader import DefinitionError, load_definitions
from footsim.defs.positions import PositionGroup, PositionGroupDef


def test_repository_definitions_load() -> None:
    defs = load_definitions()
    assert {"4-3-3", "4-2-3-1", "4-4-2"} <= set(defs.formations)
    assert {"ENG1", "ENG2", "ENG3", "ENG4"} <= set(defs.leagues)
    for group in PositionGroup:
        assert defs.roles_for(group), f"no roles for {group}"


def test_pyramid_sizes_are_preserved() -> None:
    leagues = load_definitions().leagues
    assert leagues["ENG1"].relegations_to("ENG2") == leagues["ENG2"].promotions_to("ENG1") == 3
    assert leagues["ENG2"].relegations_to("ENG3") == leagues["ENG3"].promotions_to("ENG2") == 3
    assert leagues["ENG3"].relegations_to("ENG4") == leagues["ENG4"].promotions_to("ENG3") == 4


def test_championship_playoffs_cover_third_to_eighth() -> None:
    playoffs = load_definitions().leagues["ENG2"].playoffs
    assert len(playoffs) == 1
    assert playoffs[0].entrant_ranks() == {3, 4, 5, 6, 7, 8}


def test_weights_must_sum_to_one() -> None:
    with pytest.raises(ValidationError, match="sum to 1.0"):
        PositionGroupDef(group=PositionGroup.ST, weights={"finishing": 0.5, "off_ball": 0.4})


def test_unknown_attribute_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown attributes"):
        PositionGroupDef(group=PositionGroup.ST, weights={"finishing": 0.5, "shooting": 0.5})


def test_formation_needs_eleven_slots() -> None:
    slots = [
        {"id": f"S{i}", "position": "CB", "default_role": "central_defender",
         "base": Point(x=0.2, y=0.1 * i)}
        for i in range(9)
    ]
    slots.append({"id": "GK", "position": "GK", "default_role": "goalkeeper",
                  "base": Point(x=0.04, y=0.5)})
    with pytest.raises(ValidationError, match="11 slots"):
        FormationDef.model_validate({"key": "bad", "name": "Bad", "slots": slots})


def test_playoff_cannot_reference_later_tie() -> None:
    semi = {"id": "SF1", "a": {"rank": 3}, "b": {"winner_of": ["F"]}}
    final = {"id": "F", "a": {"rank": 1}, "b": {"rank": 2}}
    with pytest.raises(ValidationError, match="later/unknown"):
        PlayoffDef.model_validate({
            "key": "PO", "name": "PO",
            "rounds": [{"name": "SF", "ties": [semi]}, {"name": "Final", "ties": [final]}],
        })


def test_choosing_among_ties_requires_pick() -> None:
    with pytest.raises(ValidationError, match="pick"):
        EntrantRef.model_validate({"winner_of": ["E1", "E2"]})


@pytest.fixture
def config_copy(tmp_path: Path) -> Path:
    target = tmp_path / "config"
    shutil.copytree(config_dir(), target)
    return target


def _edit_yaml(path: Path, edit: object) -> None:
    data = yaml.safe_load(path.read_text())
    edit(data)  # type: ignore[operator]
    path.write_text(yaml.safe_dump(data))


def test_formation_role_must_fit_position(config_copy: Path) -> None:
    def put_striker_in_goal(data: dict) -> None:  # type: ignore[type-arg]
        data["slots"][0]["default_role"] = "poacher"

    _edit_yaml(config_copy / "formations" / "4-4-2.yaml", put_striker_in_goal)
    with pytest.raises(DefinitionError, match="does not fit position GK"):
        load_definitions(config_copy)


def test_unbalanced_promotion_detected(config_copy: Path) -> None:
    def relegate_four(data: dict) -> None:  # type: ignore[type-arg]
        data["movements"][0]["ranks"] = [17, 20]

    _edit_yaml(config_copy / "competitions" / "eng" / "premier_league.yaml", relegate_four)
    with pytest.raises(DefinitionError, match="ENG1 relegates 4 to ENG2"):
        load_definitions(config_copy)


def test_a_league_must_name_a_calendar_that_exists(config_copy: Path) -> None:
    def unplug_calendar(data: dict) -> None:  # type: ignore[type-arg]
        data["calendar"] = "NOWHERE-2026-27"

    _edit_yaml(config_copy / "competitions" / "eng" / "premier_league.yaml", unplug_calendar)
    with pytest.raises(DefinitionError, match="league ENG1: unknown calendar NOWHERE-2026-27"):
        load_definitions(config_copy)


def _edit_finance(config_copy: Path, edit: object) -> None:
    _edit_yaml(config_copy / "finance" / "finance.yaml", edit)


def test_every_cup_has_prize_money_for_each_of_its_rounds() -> None:
    defs = load_definitions()
    assert set(defs.finance.cup_prizes) == set(defs.cups)
    for key, cup in defs.cups.items():
        assert len(defs.finance.cup_prizes[key]) == len(cup.rounds), key


def test_a_cup_with_no_prize_money_is_an_error(config_copy: Path) -> None:
    def forget_the_fa_cup(data: dict) -> None:  # type: ignore[type-arg]
        del data["cup_prizes"]["FA_CUP"]

    _edit_finance(config_copy, forget_the_fa_cup)
    with pytest.raises(DefinitionError, match="cup FA_CUP: no cup_prizes"):
        load_definitions(config_copy)


def test_prize_money_needs_an_amount_for_every_round(config_copy: Path) -> None:
    def one_round_short(data: dict) -> None:  # type: ignore[type-arg]
        data["cup_prizes"]["FA_CUP"] = data["cup_prizes"]["FA_CUP"][:-1]

    _edit_finance(config_copy, one_round_short)
    with pytest.raises(DefinitionError, match="cup FA_CUP: cup_prizes has 7 amounts for 8 rounds"):
        load_definitions(config_copy)


def test_prize_money_for_a_cup_that_does_not_exist_is_an_error(config_copy: Path) -> None:
    def invent_a_cup(data: dict) -> None:  # type: ignore[type-arg]
        data["cup_prizes"]["SUPER_CUP"] = [1000.0, 2000.0]

    _edit_finance(config_copy, invent_a_cup)
    with pytest.raises(DefinitionError, match="cup_prizes for unknown cup SUPER_CUP"):
        load_definitions(config_copy)


def test_cup_prize_money_never_falls_from_one_round_to_the_next(config_copy: Path) -> None:
    def pay_the_final_least(data: dict) -> None:  # type: ignore[type-arg]
        prizes = data["cup_prizes"]["FA_CUP"]
        prizes[-1] = prizes[0] / 2

    _edit_finance(config_copy, pay_the_final_least)
    with pytest.raises(DefinitionError, match="must not fall from one round to the next"):
        load_definitions(config_copy)
