"""US college soccer (W9a): the NCAA Division I men's season and MLS's SuperDraft pool.

The interface for the draft (W9a B5):
- ``draft_pool(conn, world, meta, season_id)``: the season's prospects still to be picked
  (``DraftProspect``: player id, name, college, class, age, position, overall, potential, and
  the Generation adidas flag), best first. The pool is declared after the College Cup.
- ``turn_pro(conn, meta, player_id, day)``: a prospect leaves college as a free agent, whom a
  club can then sign (``world/transfers.py`` refuses college players until then).
- Prospects nobody drafted become free agents on the spring's release day
  (``release_undrafted``), and retire if still unsigned after a grace period.

The names are loaded on first use, so the low-level modules that import ``world.college.common``
(finance, transfers, the market) don't pull in the rest of the college game."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from footsim.world.college.draft import (
        DraftProspect,
        draft_pool,
        release_undrafted,
        turn_pro,
    )

__all__ = ["DraftProspect", "draft_pool", "release_undrafted", "turn_pro"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from footsim.world.college import draft

        return getattr(draft, name)
    raise AttributeError(name)
