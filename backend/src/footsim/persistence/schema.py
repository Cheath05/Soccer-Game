"""SQLite schema (SQLAlchemy Core). One database per save slot; see docs/adr/0001.

Conventions: integer surrogate keys; dates as ISO-8601 TEXT; money as INTEGER euro cents;
attributes as one wide row per player (a column per attribute).
"""

from sqlalchemy import (
    Column,
    Float,
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

SCHEMA_VERSION = 8  # bump on any schema change and add a step to persistence/migrations.py

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
    Column("retired_on", Text),  # the day he retired (or left the professional game)
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


# --- Career runtime ------------------------------------------------------------------

fixture = Table(
    "fixture",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("season_id", ForeignKey("season.id"), nullable=False),
    Column("competition_id", ForeignKey("competition.id"), nullable=False),
    Column("stage", Text, nullable=False),  # "league" or a play-off key such as ENG2_PO
    Column("round", Integer, nullable=False),  # league matchday, or play-off round index
    Column("tie", Text),  # play-off tie id (E1, SF1, F)
    Column("leg", Integer),  # 1 or 2 for two-legged ties
    Column("date", Text, nullable=False),
    Column("home_club_id", ForeignKey("club.id"), nullable=False),
    Column("away_club_id", ForeignKey("club.id"), nullable=False),
    Column("neutral", Integer, nullable=False, default=0),
    Column("status", Text, nullable=False),  # scheduled | played
    Column("home_goals", Integer),
    Column("away_goals", Integer),
    Column("extra_time", Integer),
    Column("home_pens", Integer),
    Column("away_pens", Integer),
    Column("sim", Text),  # quick | live | instant
    Column("stats", Text),  # JSON {"home": TeamStats, "away": TeamStats}
    Index("ix_fixture_date", "date"),
    Index("ix_fixture_comp", "competition_id", "season_id", "stage"),
    Index("ix_fixture_home", "home_club_id"),
    Index("ix_fixture_away", "away_club_id"),
)

playoff_tie = Table(
    "playoff_tie",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("season_id", ForeignKey("season.id"), nullable=False),
    Column("competition_id", ForeignKey("competition.id"), nullable=False),
    Column("playoff_key", Text, nullable=False),
    Column("tie", Text, nullable=False),
    Column("round", Integer, nullable=False),
    Column("club_a_id", ForeignKey("club.id"), nullable=False),  # higher league rank
    Column("club_b_id", ForeignKey("club.id"), nullable=False),
    Column("rank_a", Integer, nullable=False),
    Column("rank_b", Integer, nullable=False),
    Column("winner_club_id", ForeignKey("club.id")),
    UniqueConstraint("season_id", "playoff_key", "tie"),
)

league_final = Table(
    "league_final",
    metadata,
    Column("season_id", ForeignKey("season.id"), nullable=False),
    Column("competition_id", ForeignKey("competition.id"), nullable=False),
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("position", Integer, nullable=False),
    Column("played", Integer, nullable=False),
    Column("won", Integer, nullable=False),
    Column("drawn", Integer, nullable=False),
    Column("lost", Integer, nullable=False),
    Column("goals_for", Integer, nullable=False),
    Column("goals_against", Integer, nullable=False),
    Column("points", Integer, nullable=False),
    Column("outcome", Text),  # champion | promoted | playoff_winner | relegated | None
    PrimaryKeyConstraint("season_id", "competition_id", "club_id"),
)

match_event = Table(
    "match_event",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("fixture_id", ForeignKey("fixture.id"), nullable=False),
    Column("minute", Integer, nullable=False),
    # goal | own_goal | penalty_goal | penalty_miss | yellow | red | sub | injury
    Column("type", Text, nullable=False),
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("player_id", ForeignKey("player.person_id")),
    Column("other_player_id", ForeignKey("player.person_id")),  # assist, or player coming on
    Column("detail", Text),
    Column("period", Integer),  # 1-4 (v3); NULL when the engine only knew the minute
    Column("second", Integer),  # seconds into the period (v3)
    Index("ix_match_event_fixture", "fixture_id"),
)

player_match = Table(
    "player_match",
    metadata,
    Column("fixture_id", ForeignKey("fixture.id"), nullable=False),
    Column("player_id", ForeignKey("player.person_id"), nullable=False),
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("started", Integer, nullable=False),
    Column("minutes", Integer, nullable=False),
    Column("goals", Integer, nullable=False, default=0),
    Column("assists", Integer, nullable=False, default=0),
    Column("shots", Integer, nullable=False, default=0),
    Column("shots_on_target", Integer, nullable=False, default=0),
    Column("passes", Integer, nullable=False, default=0),
    Column("passes_completed", Integer, nullable=False, default=0),
    Column("tackles", Integer, nullable=False, default=0),
    Column("interceptions", Integer, nullable=False, default=0),
    Column("saves", Integer, nullable=False, default=0),
    Column("yellow", Integer, nullable=False, default=0),
    Column("red", Integer, nullable=False, default=0),
    Column("rating", Float, nullable=False),
    PrimaryKeyConstraint("fixture_id", "player_id"),
    Index("ix_player_match_player", "player_id"),
)

player_state = Table(
    "player_state",
    metadata,
    Column("player_id", ForeignKey("player.person_id"), primary_key=True),
    Column("condition", Float, nullable=False),  # 0-100 match fitness
    Column("form", Float, nullable=False),  # rolling average match rating
    Column("injured_until", Text),  # date the player is fit again
    Column("injury", Text),
    Column("suspended_matches", Integer, nullable=False, default=0),
    Column("season_yellows", Integer, nullable=False, default=0),
)

# A player's development traits, drawn once (people/development.py), and the progress he has
# built up towards his next whole-point move.
cup_tie = Table(
    "cup_tie",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("season_id", ForeignKey("season.id"), nullable=False),
    Column("competition_id", ForeignKey("competition.id"), nullable=False),
    Column("round", Integer, nullable=False),  # 0-based, as the cup's rounds are listed
    Column("tie", Text, nullable=False),  # "1", "2", ... in draw order; "B1"... for byes
    Column("club_a_id", ForeignKey("club.id"), nullable=False),  # drawn first: at home first
    Column("club_b_id", ForeignKey("club.id")),  # None: a bye (club A is exempt)
    Column("winner_club_id", ForeignKey("club.id")),
    UniqueConstraint("season_id", "competition_id", "round", "tie"),
)

player_development = Table(
    "player_development",
    metadata,
    Column("player_id", ForeignKey("player.person_id"), primary_key=True),
    Column("peak_age", Float, nullable=False),
    Column("decline_age", Float, nullable=False),
    Column("ceiling_bonus", Integer, nullable=False),
    Column("ageless", Integer, nullable=False),
    Column("progress", Float, nullable=False),
    # recent monthly change in his overall, smoothed (development.yaml trend_memory): the
    # up/down arrow next to his overall
    Column("trend", Float, nullable=False, server_default="0"),
)

tactic = Table(
    "tactic",
    metadata,
    Column("club_id", ForeignKey("club.id"), primary_key=True),
    Column("formation", Text, nullable=False),
    Column("roles", Text, nullable=False),  # JSON {slot id: role key}
    Column("lineup", Text),  # JSON {slot id: player id}, None = pick automatically
    Column("instructions", Text, nullable=False),  # JSON {instruction: level}
)
