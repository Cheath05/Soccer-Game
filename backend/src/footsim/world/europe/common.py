"""What the European competitions' parts share: their competition rows, the season's dates,
and the fixtures' round numbers."""

from datetime import date
from typing import Any

from sqlalchemy import Connection, Row, select

from footsim.competitions.calendars import season_label, shift_keep_weekday
from footsim.defs.europe import ContinentalDatesDef, ContinentalDef, EuropeCalendarDef
from footsim.persistence.schema import competition, fixture
from footsim.world.context import World

# A European fixture's round: 0 the summer play-off round, 1-8 the league phase's matchdays,
# KNOCKOUT + n the n-th knockout round (the play-off first, the final last).
QUALIFYING = 0
KNOCKOUT = 100


def enabled(world: World) -> bool:
    return world.defs.europe.enabled


def competitions_by_rank(world: World) -> list[ContinentalDef]:
    return sorted(world.defs.continental.values(), key=lambda c: c.rank)


def competition_id(conn: Connection, comp: ContinentalDef) -> int:
    """A European competition's row, added the first time it's played."""
    existing = conn.execute(select(competition.c.id).where(competition.c.key == comp.key)).first()
    if existing is not None:
        return int(existing.id)
    inserted = conn.execute(competition.insert().values(
        key=comp.key, name=comp.name, short_name=comp.short_name, nation_id=None,
        type="continental", tier=None, sim_level="playable"))
    key = inserted.inserted_primary_key
    assert key is not None
    return int(key[0])


def europe_calendar(world: World, season_id: int) -> EuropeCalendarDef:
    """The European dates of season ``season_id``: the calendar in the data, moved on by whole
    years with the weekdays kept, as the countries' calendars are."""
    base = world.defs.europe_calendars[world.defs.europe.calendar]
    years = season_id - 1
    if years == 0:
        return base

    def days(legs: list[list[date]]) -> list[list[date]]:
        return [[shift_keep_weekday(day, years) for day in leg] for leg in legs]

    return EuropeCalendarDef(
        key=f"UEFA-{season_label(base.season_start.year + years)}",
        season=season_label(base.season_start.year + years),
        season_start=base.season_start.replace(year=base.season_start.year + years),
        competitions={key: ContinentalDatesDef(
            qualifying=days(c.qualifying), league_phase=days(c.league_phase),
            knockout=[days(rnd) for rnd in c.knockout])
            for key, c in base.competitions.items()})


def is_european(world: World, fx: Row[Any]) -> bool:
    return bool(fx.stage in world.defs.continental)


def stage_fixtures(conn: Connection, season_id: int, comp_key: str, round_number: int
                   ) -> list[Row[Any]]:
    return list(conn.execute(select(fixture).where(
        fixture.c.season_id == season_id, fixture.c.stage == comp_key,
        fixture.c.round == round_number).order_by(fixture.c.id)).all())
