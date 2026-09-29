"""Loads and cross-validates every game-definition file under data/config.

Each file is validated on its own by its Pydantic model; this module then checks references
*between* files (formation slots -> positions/roles, league movements -> other leagues, etc.)
so a broken mod fails loudly at startup instead of mid-season.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from footsim.core.paths import config_dir
from footsim.defs.calendar import SeasonCalendarDef
from footsim.defs.competitions import LeagueDef
from footsim.defs.finance import WageLevelsFile
from footsim.defs.formations import FormationDef
from footsim.defs.match import (
    DuelsDef,
    HomeAdvantageDef,
    InstructionDef,
    PassingDef,
    PresentationDef,
    QuickEngineParams,
    RestartsDef,
    TacticsDef,
)
from footsim.defs.nations import NationDef, NationsFile
from footsim.defs.positions import AdjacencyDef, PositionDef, PositionGroup, PositionsFile
from footsim.defs.roles import RoleDef
from footsim.defs.world_build import WorldBuildRules
from footsim.domain.personality import PERSONALITY_TRAITS


class DefinitionError(Exception):
    pass


@dataclass(frozen=True)
class GameDefinitions:
    positions: dict[str, PositionDef]
    group_weights: dict[PositionGroup, dict[str, float]]
    adjacency: list[AdjacencyDef]
    roles: dict[str, RoleDef]
    formations: dict[str, FormationDef]
    leagues: dict[str, LeagueDef]
    calendars: dict[str, SeasonCalendarDef]
    nations: dict[str, NationDef]
    world_build: WorldBuildRules
    wage_levels: WageLevelsFile
    quick_engine: QuickEngineParams
    instructions: dict[str, InstructionDef]
    presentation: PresentationDef
    restarts: RestartsDef
    duels: DuelsDef
    passing: PassingDef
    tactics: TacticsDef
    home_advantage: HomeAdvantageDef

    def roles_for(self, group: PositionGroup) -> list[RoleDef]:
        return [r for r in self.roles.values() if r.group is group]


def _read_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _validate[M: BaseModel](model: type[M], raw: Any, path: Path) -> M:
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise DefinitionError(f"{path}: {exc}") from exc


def _parse[M: BaseModel](model: type[M], path: Path) -> M:
    return _validate(model, _read_yaml(path), path)


def _load_dir[M: BaseModel](model: type[M], directory: Path, key_attr: str = "key") -> dict[str, M]:
    """Load every YAML file in ``directory``. A file holds one definition or a list of them."""
    items: dict[str, M] = {}
    for path in sorted(directory.rglob("*.yaml")):
        raw = _read_yaml(path)
        for entry in raw if isinstance(raw, list) else [raw]:
            item = _validate(model, entry, path)
            key = getattr(item, key_attr)
            if key in items:
                raise DefinitionError(f"{path}: duplicate {model.__name__} key {key!r}")
            items[key] = item
    return items


def load_definitions(root: Path | None = None) -> GameDefinitions:
    root = root or config_dir()
    positions_file = _parse(PositionsFile, root / "positions.yaml")
    defs = GameDefinitions(
        positions={p.code: p for p in positions_file.positions},
        group_weights={g.group: dict(g.weights) for g in positions_file.groups},
        adjacency=list(positions_file.adjacency),
        roles=_load_dir(RoleDef, root / "roles"),
        formations=_load_dir(FormationDef, root / "formations"),
        leagues=_load_dir(LeagueDef, root / "competitions"),
        calendars=_load_dir(SeasonCalendarDef, root / "calendars"),
        nations={n.code: n for n in _parse(NationsFile, root / "nations.yaml").nations},
        world_build=_parse(WorldBuildRules, root / "world_build.yaml"),
        wage_levels=_parse(WageLevelsFile, root / "finance" / "wage_levels.yaml"),
        quick_engine=_parse(QuickEngineParams, root / "match" / "quick_engine.yaml"),
        instructions=_load_dir(InstructionDef, root / "match" / "instructions"),
        presentation=_parse(PresentationDef, root / "match" / "presentation.yaml"),
        restarts=_parse(RestartsDef, root / "match" / "restarts.yaml"),
        duels=_parse(DuelsDef, root / "match" / "duels.yaml"),
        passing=_parse(PassingDef, root / "match" / "passing.yaml"),
        tactics=_parse(TacticsDef, root / "match" / "tactics.yaml"),
        home_advantage=_parse(HomeAdvantageDef, root / "match" / "home_advantage.yaml"),
    )
    _cross_validate(defs)
    return defs


def _cross_validate(defs: GameDefinitions) -> None:
    errors: list[str] = []

    for group in PositionGroup:
        if not defs.roles_for(group):
            errors.append(f"position group {group} has no roles")

    for f in defs.formations.values():
        for slot in f.slots:
            pos = defs.positions.get(slot.position)
            role = defs.roles.get(slot.default_role)
            if pos is None:
                errors.append(f"formation {f.key} slot {slot.id}: unknown position {slot.position}")
            elif role is None:
                errors.append(f"formation {f.key} slot {slot.id}: unknown role {slot.default_role}")
            elif role.group is not pos.group:
                errors.append(
                    f"formation {f.key} slot {slot.id}: role {role.key} ({role.group}) "
                    f"does not fit position {pos.code} ({pos.group})"
                )

    names = [n.name for n in defs.nations.values()]
    if len(names) != len(set(names)):
        errors.append("duplicate nation names in nations.yaml")

    physique = defs.world_build.physique
    for code in set(defs.positions) - set(physique.height_by_position):
        errors.append(f"world_build physique has no height for position {code}")
    personality = defs.world_build.personality
    for trait in (set(personality.overrides) | set(personality.overall_effect_per_point)) - set(
        PERSONALITY_TRAITS
    ):
        errors.append(f"world_build personality rule for unknown trait {trait}")

    for key in ("mentality", "pressing", "line", "width", "tempo", "passing"):
        known = defs.instructions.get(key)
        levels = getattr(defs.tactics, key)
        if known is None:
            errors.append(f"tactics.yaml: no instruction {key!r} in match/instructions")
        elif set(levels) != set(known.options):
            errors.append(f"tactics.yaml {key}: levels {sorted(levels)} != {sorted(known.options)}")

    quick = defs.quick_engine
    for name in ("attack_weights", "defence_weights", "midfield_weights", "scorer_weights",
                 "assist_weights"):
        missing = set(PositionGroup) - set(getattr(quick, name))
        if missing:
            errors.append(f"quick_engine {name} lacks {sorted(missing)}")
    for key, levels in quick.instructions.items():
        known = defs.instructions.get(key)
        if known is None:
            errors.append(f"quick_engine reacts to unknown instruction {key}")
        elif set(levels) - set(known.options):
            errors.append(f"quick_engine: unknown {key} levels {set(levels) - set(known.options)}")

    for league in defs.leagues.values():
        if league.nation not in defs.nations:
            errors.append(f"league {league.key}: unknown nation code {league.nation}")
        if league.calendar not in defs.calendars:
            errors.append(f"league {league.key}: unknown calendar {league.calendar}")
        elif league.key not in defs.calendars[league.calendar].competitions:
            errors.append(f"league {league.key}: no dates in calendar {league.calendar}")
        targets = [m.to for m in league.movements] + [
            p.winner_to for p in league.playoffs if p.winner_to
        ]
        for target in targets:
            if target not in defs.leagues:
                errors.append(f"league {league.key}: movement to unknown league {target}")

    # Promotion and relegation must keep every league the same size.
    for upper in defs.leagues.values():
        for lower in defs.leagues.values():
            down = upper.relegations_to(lower.key)
            up = lower.promotions_to(upper.key)
            if down != up:
                errors.append(
                    f"{upper.key} relegates {down} to {lower.key} but {lower.key} "
                    f"promotes {up} to {upper.key}"
                )

    if errors:
        raise DefinitionError("invalid game definitions:\n  " + "\n  ".join(errors))
