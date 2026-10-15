"""What the European competitions' parts share: their competition rows, the season's dates,
and the fixtures' round numbers."""

from datetime import date
from typing import Any

from sqlalchemy import Connection, Row, select

from footsim.competitions.calendars import season_label, shift_keep_weekday
from footsim.defs.europe import (
    ContinentalDatesDef,
    ContinentalDef,
    EuropeCalendarDef,
    QualifyingRoundDef,
)
from footsim.persistence.schema import competition, fixture
from footsim.world.context import World

# A European fixture's round: the qualifying rounds -3 (Q1), -2 (Q2), -1 (Q3) and 0 (the play-off
# round), 1-8 the league phase's matchdays, KNOCKOUT + n the n-th knockout round (the knockout
# play-off first, the final last).
QUALIFYING_ROUNDS = ("Q1", "Q2", "Q3", "PO")
LEAGUE_PHASE = "LP"
QUALIFYING = 0  # the last qualifying round's number: qualifying rounds are numbered up to it
KNOCKOUT = 100


def round_number(key: str) -> int:
    """A round's fixture number: Q1 -3 ... PO 0; the league phase 1."""
    if key == LEAGUE_PHASE:
        return 1
    return QUALIFYING_ROUNDS.index(key) - (len(QUALIFYING_ROUNDS) - 1)


def round_key(number: int) -> str:
    """A fixture number's round: -3 Q1 ... 0 PO; 1 and above the league phase."""
    if number >= 1:
        return LEAGUE_PHASE
    return QUALIFYING_ROUNDS[number + len(QUALIFYING_ROUNDS) - 1]


def qualifying_round(comp: ContinentalDef, number: int) -> QualifyingRoundDef:
    return comp.qualifying[number + len(comp.qualifying) - 1]


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
            qualifying={k: days(legs) for k, legs in c.qualifying.items()},
            league_phase=days(c.league_phase), knockout=[days(rnd) for rnd in c.knockout])
            for key, c in base.competitions.items()})


def stage_name(comp: ContinentalDef, round_number: int) -> str:
    """A European fixture's stage in words: "Second qualifying round", "League phase,
    matchday 3", "Round of 16"."""
    if round_number <= QUALIFYING:
        return qualifying_round(comp, round_number).name
    if round_number < KNOCKOUT:
        return f"League phase, matchday {round_number}"
    return comp.knockout[round_number - KNOCKOUT].name


def is_european(world: World, fx: Row[Any]) -> bool:
    return bool(fx.stage in world.defs.continental)


def stage_fixtures(conn: Connection, season_id: int, comp_key: str, round_number: int
                   ) -> list[Row[Any]]:
    return list(conn.execute(select(fixture).where(
        fixture.c.season_id == season_id, fixture.c.stage == comp_key,
        fixture.c.round == round_number).order_by(fixture.c.id)).all())
