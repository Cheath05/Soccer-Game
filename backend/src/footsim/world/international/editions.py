"""The World Cup's editions (data/config/international/world_cup.yaml ``editions``): one every
four years from 2030, each with its hosts, its qualifiers (qualifiers.yaml, moved on by the
years since 2030 and changed as its hosts need) and its finals' dates.

Each edition keeps its fixtures and state apart by its names. The first (2030) keeps the names
the game gave it before there were others, so careers already under way go on: its qualifiers'
stages are ``WCQ:<stage>``, its finals' ``WCF:<round>``, game_meta ``wc_qualified``, ``wcq_done``,
``wcq_seeds:<stage>`` and ``wc_finals``, competitions ``WCQ`` and ``WC``. A later one's carry its
year: ``WCQ:2034:<stage>``, ``WCF:2034:<round>``, ``wc_qualified:2034``... and ``WCQ2034``,
``WC2034``.
"""

from dataclasses import dataclass
from datetime import date

from footsim.defs.international import QualifierStageDef, WorldCupDef
from footsim.world.context import World

QUALIFIERS = "WCQ:"  # every edition's qualifier stages start so
FINALS = "WCF:"  # and its finals' stages


@dataclass(frozen=True)
class Edition:
    year: int
    hosts: tuple[str, ...]
    stages: tuple[QualifierStageDef, ...]  # its qualifiers, windows in its own years
    dates: WorldCupDef  # its finals' dates
    first: bool  # the first edition, with the original names

    @property
    def _tag(self) -> str:
        return "" if self.first else f"{self.year}:"

    def qualifier_stage(self, key: str) -> str:
        """A qualifying stage's fixtures' ``stage``."""
        return f"{QUALIFIERS}{self._tag}{key}"

    def finals_stage(self, rnd: str) -> str:
        """A finals round's fixtures' ``stage``: G (the groups), R32 ... F, 3P."""
        return f"{FINALS}{self._tag}{rnd}"

    @property
    def groups(self) -> str:
        return self.finals_stage("G")

    def _meta(self, key: str) -> str:
        return key if self.first else f"{key}:{self.year}"

    @property
    def qualified_key(self) -> str:  # game_meta: {code: how it qualified}
        return self._meta("wc_qualified")

    @property
    def done_key(self) -> str:  # game_meta: the stages whose outcomes are recorded
        return self._meta("wcq_done")

    def seeds_key(self, key: str) -> str:  # game_meta: a path stage's seeds
        return f"wcq_seeds:{self._tag}{key}"

    @property
    def state_key(self) -> str:  # game_meta: the finals' groups, call-ups, champion
        return self._meta("wc_finals")

    @property
    def qualifiers_competition(self) -> tuple[str, str]:
        """The qualifiers' competition: (key, name)."""
        return ("WCQ" if self.first else f"WCQ{self.year}", f"World Cup {self.year} qualifiers")

    @property
    def finals_competition(self) -> tuple[str, str]:
        return ("WC" if self.first else f"WC{self.year}", f"FIFA World Cup {self.year}")

    def stage(self, key: str) -> QualifierStageDef | None:
        return next((s for s in self.stages if s.key == key), None)

    @property
    def final_day(self) -> date:
        return date.fromisoformat(self.dates.final)


_CACHE: dict[tuple[int, int], Edition] = {}


def _shift(day: str, years: int) -> str:
    d = date.fromisoformat(day)
    return d.replace(year=d.year + years).isoformat()


def edition(world: World, year: int) -> Edition:
    """The ``year`` edition (one of the World Cup's years)."""
    found = _CACHE.get((id(world.defs), year))
    if found is not None:
        return found
    spec = world.defs.international
    cup = spec.world_cup
    if not cup.is_edition(year):
        raise ValueError(f"no World Cup in {year}")
    own = cup.edition(year)
    years = year - cup.year
    dates = cup.model_copy(update={
        "year": year,
        "draw": _shift(cup.draw, years),
        "groups": [_shift(d, years) for d in cup.groups],
        **{f: _shift(getattr(cup, f), years) for f in (
            "round_of_32", "round_of_16", "quarter_finals", "semi_finals", "third_place",
            "final")}})
    found = Edition(year, tuple(own.hosts), tuple(spec.qualifiers.for_edition(year, own.stages)),
                    dates, year == cup.year)
    _CACHE[(id(world.defs), year)] = found
    return found


def next_year(world: World, year: int) -> int:
    """The first edition in ``year`` or after it."""
    cup = world.defs.international.world_cup
    if year <= cup.year:
        return cup.year
    return cup.year + -(-(year - cup.year) // cup.every_years) * cup.every_years


def qualifying(world: World, day: date) -> list[Edition]:
    """The editions whose qualifiers may have a draw or a match on ``day``: the next World Cup
    from ``day``'s year, and the one after it (its first stages may start before the next
    one's finals)."""
    year = next_year(world, day.year)
    every = world.defs.international.world_cup.every_years
    return [edition(world, year), edition(world, year + every)]


def current(world: World, day: date, keep_days: int = 0) -> Edition:
    """The edition being played on ``day`` or the next one: an edition stays current until
    ``keep_days`` after its final."""
    ed = edition(world, next_year(world, day.year))
    if (day - ed.final_day).days > keep_days:
        ed = edition(world, ed.year + world.defs.international.world_cup.every_years)
    return ed


def of_stage(world: World, stage: str) -> tuple[Edition, str] | None:
    """The edition and the stage key (or finals round) of a World Cup fixture's ``stage``."""
    for prefix in (QUALIFIERS, FINALS):
        if stage.startswith(prefix):
            rest = stage[len(prefix):]
            year, sep, key = rest.partition(":")
            if sep and year.isdigit():
                return edition(world, int(year)), key
            return edition(world, world.defs.international.world_cup.year), rest
    return None
