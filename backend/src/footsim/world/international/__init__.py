"""International football (W8, docs/plans/w8-w10-international.md).

The package's names load lazily: modules low in the import graph (world/squads.py) import
``world.international.common``, which must not pull in the team-making modules (they import
world/lifecycle.py, which imports world/squads.py)."""

from typing import Any

__all__ = ["ensure_international", "pick_squads"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from footsim.world.international import teams

        return getattr(teams, name)
    raise AttributeError(name)
