"""Completes a source player's attributes: derives the ones the source lacks and turns
PlayStyles into attribute bonuses and behavioural traits (rules in the import profile)."""

from statistics import fmean

from footsim.domain.attributes import ATTR_MAX, ATTR_MIN, ATTRIBUTES
from footsim.importers.profile import ImportProfile
from footsim.importers.records import SourcePlayer
from footsim.importers.rng import entity_rng


def _playstyle(name: str) -> tuple[str, bool]:
    """'Anticipate+' -> ('Anticipate', True)."""
    return (name[:-1], True) if name.endswith("+") else (name, False)


def complete_attributes(player: SourcePlayer, profile: ImportProfile, seed: int) -> dict[str, int]:
    values: dict[str, float] = {a: float(v) for a, v in player.attrs.items()}
    rng = entity_rng(seed, player.source, player.source_id, "derive")
    is_goalkeeper = player.position == "GK"
    gk_source = [v for a, v in values.items() if a.startswith("gk_")]
    outfield_gk_value = fmean(gk_source) if gk_source else float(ATTR_MIN)

    for attr, rule in profile.derived.items():
        noise = float(rng.normal(0.0, rule.noise_sd)) if rule.noise_sd else 0.0
        if rule.goalkeepers_only and not is_goalkeeper:
            values[attr] = outfield_gk_value
            continue
        total_weight = sum(t.w for t in rule.terms)
        base = sum(
            t.w * (values[t.attr] if t.attr else max(values[a] for a in t.max_of))
            for t in rule.terms
        )
        values[attr] = base / total_weight + noise

    for name in player.playstyles:
        style, plus = _playstyle(name)
        for attr, bonus in profile.playstyle_effects.get(style, {}).items():
            if profile.derived[attr].goalkeepers_only and not is_goalkeeper:
                continue
            values[attr] += bonus * (profile.plus_multiplier if plus else 1.0)

    return {a: int(min(ATTR_MAX, max(ATTR_MIN, round(values[a])))) for a in ATTRIBUTES}


def traits_for(player: SourcePlayer, profile: ImportProfile) -> list[str]:
    traits = {
        profile.playstyle_traits[style]
        for style, _ in map(_playstyle, player.playstyles)
        if style in profile.playstyle_traits
    }
    return sorted(traits)
