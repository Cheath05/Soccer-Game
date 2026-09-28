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
