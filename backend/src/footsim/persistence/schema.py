"""SQLite schema (SQLAlchemy Core). One database per save slot; see docs/adr/0001.

Conventions: integer surrogate keys; dates as ISO-8601 TEXT; money as INTEGER euro cents;
attributes as one wide row per player (a column per attribute).
"""

from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    SmallInteger,
    Table,
    Text,
    UniqueConstraint,
)

from footsim.domain.attributes import ATTRIBUTES
from footsim.domain.personality import PERSONALITY_TRAITS

SCHEMA_VERSION = 1

metadata = MetaData()

game_meta = Table(
    "game_meta",
    metadata,
    Column("key", Text, primary_key=True),
    Column("value", Text, nullable=False),  # JSON
)

nation = Table(
    "nation",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", Text, nullable=False, unique=True),
    Column("code", Text),
)

season = Table(
    "season",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("label", Text, nullable=False, unique=True),
    Column("start_date", Text, nullable=False),
    Column("end_date", Text, nullable=False),
)

competition = Table(
    "competition",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("key", Text, nullable=False, unique=True),
    Column("name", Text, nullable=False),
    Column("short_name", Text, nullable=False),
    Column("nation_id", ForeignKey("nation.id")),
    Column("type", Text, nullable=False),
    Column("tier", Integer),
    Column("sim_level", Text, nullable=False),
)

club = Table(
    "club",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", Text, nullable=False),
    Column("nation_id", ForeignKey("nation.id")),
    # League name from the source data; kept for clubs in leagues we don't simulate.
    Column("source_league", Text),
    Column("reputation", SmallInteger, nullable=False),
    Column("stadium_name", Text),
    Column("stadium_capacity", Integer),
)

club_league_membership = Table(
    "club_league_membership",
    metadata,
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("season_id", ForeignKey("season.id"), nullable=False),
    Column("competition_id", ForeignKey("competition.id"), nullable=False),
    PrimaryKeyConstraint("club_id", "season_id"),
)

person = Table(
    "person",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("first_name", Text, nullable=False),
    Column("last_name", Text, nullable=False),
    Column("known_as", Text),
    Column("birth_date", Text, nullable=False),
    Column("nation_id", ForeignKey("nation.id")),
    Column("birth_city", Text),
)

player = Table(
    "player",
    metadata,
    Column("person_id", ForeignKey("person.id"), primary_key=True),
    Column("height_cm", SmallInteger),
    Column("weight_kg", SmallInteger),
    Column("preferred_foot", Text, nullable=False),
    Column("weak_foot", SmallInteger, nullable=False),
    Column("skill_moves", SmallInteger, nullable=False),
    Column("pa_hidden", SmallInteger, nullable=False),
    Column("reputation", SmallInteger, nullable=False),
    Column("value_eur_cents", Integer),
)

player_attr = Table(
    "player_attr",
    metadata,
    Column("player_id", ForeignKey("player.person_id"), primary_key=True),
    *(Column(a, SmallInteger, nullable=False) for a in ATTRIBUTES),
)

player_position = Table(
    "player_position",
    metadata,
    Column("player_id", ForeignKey("player.person_id"), nullable=False),
    Column("position", Text, nullable=False),
    Column("familiarity", SmallInteger, nullable=False),
    PrimaryKeyConstraint("player_id", "position"),
)

player_personality = Table(
    "player_personality",
    metadata,
    Column("player_id", ForeignKey("player.person_id"), primary_key=True),
    *(Column(t, SmallInteger, nullable=False) for t in PERSONALITY_TRAITS),
)

player_trait = Table(
    "player_trait",
    metadata,
    Column("player_id", ForeignKey("player.person_id"), nullable=False),
    Column("trait", Text, nullable=False),
    PrimaryKeyConstraint("player_id", "trait"),
)

contract = Table(
    "contract",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("person_id", ForeignKey("person.id"), nullable=False),
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("kind", Text, nullable=False),  # player | staff | youth | loan
    Column("start_date", Text, nullable=False),
    Column("end_date", Text, nullable=False),
    Column("wage_weekly_cents", Integer, nullable=False),
    Column("release_clause_cents", Integer),
    Column("is_active", Integer, nullable=False),
    Index("ix_contract_club_active", "club_id", "is_active"),
    Index("ix_contract_person", "person_id"),
)

external_id = Table(
    "external_id",
    metadata,
    Column("entity_type", Text, nullable=False),  # player | club | competition
    Column("entity_id", Integer, nullable=False),
    Column("source", Text, nullable=False),  # ea_fc27 | transfermarkt | ...
    Column("source_id", Text, nullable=False),
    UniqueConstraint("entity_type", "source", "source_id"),
    Index("ix_external_entity", "entity_type", "entity_id"),
)
