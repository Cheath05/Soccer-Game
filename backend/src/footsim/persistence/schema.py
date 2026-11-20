"""SQLite schema (SQLAlchemy Core). One database per save slot; see docs/adr/0001.

Conventions: integer surrogate keys; dates as ISO-8601 TEXT; money as INTEGER euro cents;
attributes as one wide row per player (a column per attribute).
"""

from sqlalchemy import (
    DDL,
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
    event,
    text,
)

from footsim.domain.attributes import ATTRIBUTES
from footsim.domain.personality import PERSONALITY_TRAITS

SCHEMA_VERSION = 29  # bump on any schema change and add a step to persistence/migrations.py

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
    Column("value_eur_cents", Integer),  # Transfermarkt's, from the world build (W4-1's fit)
    Column("retired_on", Text),  # the day he retired (or left the professional game)
    # His market premium over the value model (log), from his Transfermarkt value: the fame the
    # ratings don't see (transfers/valuation.py). None until worked out; 0 for none.
    Column("value_premium", Float),
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
    Column("listed", Integer, nullable=False, server_default="0"),  # transfer-listed (W4)
    # Up for loan: the user offers him to clubs that need cover (AI clubs lend only surplus).
    Column("loan_listed", Integer, nullable=False, server_default="0"),
    Index("ix_contract_club_active", "club_id", "is_active"),
    Index("ix_contract_person", "person_id"),
    # One club owns a player: at most one active contract per person that isn't a loan (W4-3).
    Index("ux_contract_owner", "person_id", unique=True,
          sqlite_where=text("is_active = 1 AND kind != 'loan'")),
    # And at most one active loan (W4-8): a loan is a contract row of kind 'loan' at the
    # borrowing club, beside his permanent contract at the parent club.
    Index("ux_contract_loan", "person_id", unique=True,
          sqlite_where=text("is_active = 1 AND kind = 'loan'")),
)

# Where each player plays (W4-8): his active loan if he has one, else his permanent contract.
# Every squad reads this, so a loaned player is in exactly one squad.
PLAYING_VIEW = """
CREATE VIEW IF NOT EXISTS playing AS
SELECT k.* FROM contract k
WHERE k.is_active = 1 AND (k.kind = 'loan' OR NOT EXISTS (
    SELECT 1 FROM contract l WHERE l.person_id = k.person_id AND l.is_active = 1
    AND l.kind = 'loan'))
"""
event.listen(metadata, "after_create", DDL(PLAYING_VIEW))  # type: ignore[no-untyped-call]

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
    # A college home game's crowd in the program builder mode (W9d, v28); None otherwise.
    Column("attendance", Integer),
    Column("stats", Text),  # JSON {"home": TeamStats, "away": TeamStats}
    Index("ix_fixture_date", "date"),
    Index("ix_fixture_comp", "competition_id", "season_id", "stage"),
    Index("ix_fixture_home", "home_club_id"),
    Index("ix_fixture_away", "away_club_id"),
    # a tie's legs (europe/ties.py tie_winner, cups): found without scanning every season's
    Index("ix_fixture_tie", "season_id", "stage", "round", "tie"),
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

# Every league title won (W9a): a league's champions, a phase's (Apertura, Clausura), a title
# play-off's winners (MLS Cup) and a table's own title when the champion is decided otherwise
# (the Supporters' Shield). ``kind``: champion | award.
league_title = Table(
    "league_title",
    metadata,
    Column("season_id", ForeignKey("season.id"), nullable=False),
    Column("competition_id", ForeignKey("competition.id"), nullable=False),
    Column("title", Text, nullable=False),
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("kind", Text, nullable=False),
    Column("phase", Text),
    Column("won_on", Text),
    PrimaryKeyConstraint("season_id", "competition_id", "title"),
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
    # Development minutes credited for being named a substitute without coming on, a running
    # total that fades every month (development.yaml bench_credit_minutes, bench_decay). Every
    # player has a row here from the day a career starts, so results can credit it at once.
    Column("bench_minutes", Float, nullable=False, server_default="0"),
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
    Column("path", Text),  # a European qualifying round's path (v20): champions, league, main
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
    # The potential the academy boost has added so far (development.yaml academy_*), fractions
    # included: the whole points of it are already in his pa_hidden.
    Column("potential_boost", Float, nullable=False, server_default="0"),
)

# Each player's overall on the day a season began (world/overall_history.py): the "before" of the
# season summary's development table. The next season's row is his overall at this one's end.
player_season_overall = Table(
    "player_season_overall",
    metadata,
    Column("season_id", ForeignKey("season.id"), nullable=False),
    Column("player_id", ForeignKey("player.person_id"), nullable=False),
    Column("overall", SmallInteger, nullable=False),  # in his best position's group, as shown
    # The game date it was taken: the season's first day, unless the career began keeping the
    # record part-way through a season (an upgraded save).
    Column("recorded_on", Text, nullable=False),
    PrimaryKeyConstraint("season_id", "player_id"),
)

# A club's money (W3, world/finance.py). The balance is the source of truth for cash and always
# equals the sum of the club's ledger; the wage bill is never stored (it's the sum of the active
# contracts).
transfer = Table(
    "transfer",  # every completed move (W4): the history, and the reference for the money
    metadata,
    Column("id", Integer, primary_key=True),
    Column("player_id", ForeignKey("player.person_id"), nullable=False),
    Column("from_club_id", ForeignKey("club.id")),  # None: he was a free agent
    Column("to_club_id", ForeignKey("club.id")),  # None: released into free agency
    Column("date", Text, nullable=False),
    Column("season_id", Integer, nullable=False),
    Column("kind", Text, nullable=False),  # transfer | free | release | loan | loan_return
    Column("fee_cents", Integer, nullable=False),
    Column("wage_weekly_cents", Integer, nullable=False),
    Column("contract_end", Text),
    Column("by_user", Integer, nullable=False),  # 1 when the user's club made the move
    Index("ix_transfer_player", "player_id"),
    Index("ix_transfer_season", "season_id"),
    Index("ix_transfer_date", "date"),  # the market's recent moves (market.py counts)
)

transfer_offer = Table(
    "transfer_offer",  # offers that outlive a click: bids for the user's players, and replies due
    metadata,
    Column("id", Integer, primary_key=True),
    Column("player_id", ForeignKey("player.person_id"), nullable=False),
    Column("bidder_club_id", ForeignKey("club.id"), nullable=False),
    Column("owner_club_id", ForeignKey("club.id")),  # None: a free agent
    Column("kind", Text, nullable=False),  # transfer | loan
    Column("status", Text, nullable=False),  # pending | accepted | rejected | countered | ...
    Column("fee_cents", Integer, nullable=False),
    Column("counter_fee_cents", Integer),
    Column("wage_weekly_cents", Integer),
    Column("years", SmallInteger),
    Column("created", Text, nullable=False),
    Column("expires", Text, nullable=False),
    Column("by_user", Integer, nullable=False),
    # The user's haggling (W4 follow-up): the rounds of offers so far in these talks.
    Column("rounds", Integer, nullable=False, server_default="0"),
    Index("ix_transfer_offer_owner", "owner_club_id", "status"),
)

position_training = Table(
    "position_training",  # a player learning a position (the user's choice), a month at a time
    metadata,
    Column("player_id", ForeignKey("player.person_id"), primary_key=True),
    Column("position", Text, nullable=False),
    Column("progress", Float, nullable=False, server_default="0"),  # toward the next point
    Column("started", Text, nullable=False),
)

club_finance = Table(
    "club_finance",
    metadata,
    Column("club_id", ForeignKey("club.id"), primary_key=True),
    Column("balance_cents", Integer, nullable=False),
    Column("club_income_cents", Integer, nullable=False),  # a season's commercial and matchday
    Column("transfer_budget_cents", Integer, nullable=False),
    Column("wage_budget_cents", Integer, nullable=False),  # a week's wages the board allows
    Column("budget_season_id", Integer, nullable=False),  # the season the budgets were set for
    Column("board_target", SmallInteger),  # the league position the board expects
    Column("board_confidence", SmallInteger),  # 0-100
    Column("settled_on", Text),  # the last monthly settlement (so a day is never paid twice)
)

# Every change to a club's balance, with what it was for: opening | broadcast | club_income |
# wages | operating | prize | parachute | transfer | adjustment. Append-only.
finance_ledger = Table(
    "finance_ledger",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("date", Text, nullable=False),
    Column("season_id", Integer, nullable=False),
    Column("kind", Text, nullable=False),
    Column("amount_cents", Integer, nullable=False),
    Column("ref_id", Integer),  # what it refers to (a competition, a transfer)
    Index("ix_finance_ledger_club", "club_id", "season_id"),
)

# The user's saved tactics: a name, and the tactic as the tactic table keeps it (the line-up
# only when saved with it).
tactic_preset = Table(
    "tactic_preset",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("name", Text, nullable=False),
    Column("formation", Text, nullable=False),
    Column("roles", Text, nullable=False),
    Column("lineup", Text),
    Column("instructions", Text, nullable=False),
    Column("saved", Text, nullable=False),  # the game date it was saved
    UniqueConstraint("club_id", "name", name="ux_tactic_preset_name"),
)

# The European competitions (world/europe/, docs/plans/w6-european-competitions.md): who is in
# which competition each season, and how they got there. A club is in one a season.
continental_entry = Table(
    "continental_entry",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("season_id", ForeignKey("season.id"), nullable=False),
    Column("competition_id", ForeignKey("competition.id"), nullable=False),
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("stage", Text, nullable=False),  # qualifying | league_phase | out
    # How the place was earned: league:ENG:4, cup:FA_CUP, holder:UCL, fill:ENG,
    # qualifying (won the play-off round), dropped:UCL (lost the UCL's)
    Column("route", Text, nullable=False),
    Column("pot", Integer),  # the league-phase pot, once drawn
    Column("position", Integer),  # where it finished in the league phase, once it's over
    # The country whose place it took (nation code; v19): its points count for that country's
    # coefficient. None in older saves: the club's league's country stands in.
    Column("association", Text),
    # Where it is now (v20): the round (-3 Q1 ... 0 the play-off, 1 the league phase) and path
    # (champions, league, main) of its competition; where it started (UCL:Q2:champions) and the
    # round it dropped from into this competition, if it did (UCL:Q1:champions).
    Column("entry_round", Integer),
    Column("path", Text),
    Column("entered", Text),
    Column("came_from", Text),
    UniqueConstraint("season_id", "club_id", name="ux_continental_entry_club"),
)

# Points towards a club's European coefficient, per season (world/europe/coefficients.py).
club_coefficient = Table(
    "club_coefficient",
    metadata,
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("season_id", ForeignKey("season.id"), nullable=False),
    Column("points", Float, nullable=False),
    PrimaryKeyConstraint("club_id", "season_id"),
)

# A country's coefficient for a season played in the game (world/europe/ranking.py): its clubs'
# points and how many clubs it entered. Seasons before the career are in the definitions.
association_coefficient = Table(
    "association_coefficient",
    metadata,
    Column("nation_id", ForeignKey("nation.id"), nullable=False),
    Column("season_id", ForeignKey("season.id"), nullable=False),
    Column("points", Float, nullable=False),
    Column("clubs", Integer, nullable=False),
    PrimaryKeyConstraint("nation_id", "season_id"),
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

# --- US college soccer (W9a, the NCAA season: world/college/) ---------------------------------
# The college programs: clubs without finances or a league, in a conference, with a program
# level (the mean overall it recruits to).
college_team = Table(
    "college_team",
    metadata,
    Column("club_id", ForeignKey("club.id"), primary_key=True),
    Column("conference", Text, nullable=False),  # its key in data/config/college/ncaa_d1.yaml
    Column("tier", Integer, nullable=False),  # 1 (a national power) to 5
    Column("level", Float, nullable=False),
    # Its standing with recruits, 0-100 (W9c, v27): from its tier, then moved by its results.
    Column("prestige", Float),
)

# Every college player, past and present. ``status``: enrolled (on a college roster) | prospect
# (declared for the draft, still on the roster) | pro (turned pro: drafted or signed) |
# undrafted (left college unsigned: a free agent). Enrolled or a prospect, he is outside the
# professional game: no market, loans, renewals or wages.
college_player = Table(
    "college_player",
    metadata,
    Column("player_id", ForeignKey("person.id"), primary_key=True),
    Column("club_id", ForeignKey("club.id"), nullable=False),  # his college program
    Column("class_year", Integer, nullable=False),  # 1 Fr, 2 So, 3 Jr, 4 Sr
    Column("status", Text, nullable=False),
    Column("ga", Integer, nullable=False, server_default="0"),  # an underclassman who declared
    Column("entered_season", Integer, nullable=False),
    Column("declared_season", Integer),  # the season whose draft pool he is in
    Column("left_on", Text),  # the day he left college (turned pro or went undrafted)
    # His scholarship, as a share of a full one (W9c, v27): 0 for a walk-on.
    Column("scholarship", Float, nullable=False, server_default="0"),
    Index("ix_college_player_status", "status"),
)

# Who is in a college event of a season, and how: a conference tournament (``CT:<key>``) or the
# NCAA tournament (``NCAA``). ``seed`` is the bracket position (1 = top); ``bid``: auto |
# at_large for the NCAA; ``rank`` and ``rating``: the RPI the field was picked by.
college_entry = Table(
    "college_entry",
    metadata,
    Column("season_id", ForeignKey("season.id"), nullable=False),
    Column("event", Text, nullable=False),
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("seed", Integer, nullable=False),
    Column("bid", Text),
    Column("rank", Integer),
    Column("rating", Float),
    PrimaryKeyConstraint("season_id", "event", "club_id"),
)

# High-school recruiting (W9c, world/college/recruiting.py, v27). A recruit is a high-school
# senior of the class that enrolls at ``class_season``'s start; he becomes a player only when he
# enrolls (``player_id``). ``overall`` and ``potential`` are the truth (hidden), ``grade`` the
# recruiting services' (public), which sets the ranks and stars. ``state`` is his home state (a US
# state code), or NULL for a recruit from abroad. ``status``: open | committed | signed |
# enrolled | gone (went elsewhere: D-II, NAIA, junior college). ``club_id`` and ``share``: the
# program he committed or signed to, and his scholarship there.
recruit = Table(
    "recruit",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("class_season", Integer, nullable=False),
    Column("first_name", Text, nullable=False),
    Column("last_name", Text, nullable=False),
    Column("nation_id", ForeignKey("nation.id"), nullable=False),
    Column("state", Text),
    Column("position", Text, nullable=False),
    Column("birth_date", Text, nullable=False),
    Column("overall", Float, nullable=False),
    Column("potential", Integer, nullable=False),
    Column("grade", Float, nullable=False),
    Column("stars", Integer, nullable=False),
    Column("national_rank", Integer, nullable=False),
    Column("position_rank", Integer, nullable=False),
    Column("state_rank", Integer),
    Column("priorities", Text, nullable=False),  # JSON: each decision part's weight, about 1
    Column("readiness", Float, nullable=False, server_default="0"),
    Column("status", Text, nullable=False),
    Column("club_id", ForeignKey("club.id")),
    Column("share", Float),
    Column("committed_on", Text),
    Column("signed_on", Text),
    Column("player_id", ForeignKey("person.id")),
    Index("ix_recruit_class", "class_season", "status"),
)

# A program's scholarship offer to a recruit: one per program, changed in place. ``status``:
# open | pulled | accepted | declined.
recruit_offer = Table(
    "recruit_offer",
    metadata,
    Column("recruit_id", ForeignKey("recruit.id"), nullable=False),
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("share", Float, nullable=False),
    Column("made_on", Text, nullable=False),
    Column("status", Text, nullable=False),
    PrimaryKeyConstraint("recruit_id", "club_id"),
)

# A program recruiting a recruit: his interest in it (0-100), its priority on him (top | high |
# watch; NULL once it stops), what the user's staff know of him (0-1; the user's program only),
# the last week it put effort in, the day he visited the campus, and his personal fit to the
# program (a seeded draw, part of how he scores its offer).
recruit_interest = Table(
    "recruit_interest",
    metadata,
    Column("recruit_id", ForeignKey("recruit.id"), nullable=False),
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("interest", Float, nullable=False, server_default="0"),
    Column("priority", Text),
    Column("knowledge", Float, nullable=False, server_default="0"),
    Column("effort_on", Text),
    Column("visited_on", Text),
    Column("fit", Float, nullable=False, server_default="0"),
    PrimaryKeyConstraint("recruit_id", "club_id"),
    Index("ix_recruit_interest_club", "club_id"),
)

# The NCAA program builder mode (W9d, world/college/program.py, v28). Each program's money (in
# euro cents, as everywhere) and next season's class budget (in full scholarships: what recruiting
# may spend), its facilities (a level, and a level being built that's ready at the start of
# ``ready_season``), and its ledger.
college_program = Table(
    "college_program",
    metadata,
    Column("club_id", ForeignKey("club.id"), primary_key=True),
    Column("balance_cents", Integer, nullable=False),
    Column("class_budget", Float, nullable=False),
)

college_facility = Table(
    "college_facility",
    metadata,
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("kind", Text, nullable=False),  # training | stadium
    Column("level", Integer, nullable=False),
    Column("building_to", Integer),
    Column("ready_season", Integer),
    PrimaryKeyConstraint("club_id", "kind"),
)

# kind: allocation | tickets | boosters | ncaa | scholarships | staff | upkeep | travel | build
college_ledger = Table(
    "college_ledger",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("season_id", Integer, nullable=False),
    Column("date", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("amount_cents", Integer, nullable=False),
    Column("fixture_id", ForeignKey("fixture.id")),
    Index("ix_college_ledger_club", "club_id", "season_id"),
)

# MLS's roster rules (world/mls.py, data/config/rules/mls.yaml; v23). Money in euro cents, as
# everywhere: MLS's dollar figures are converted at the dollar rate.
# A club's season under the rules: its roster model, its allocation money and its international
# slots (traded for the season).
mls_club_season = Table(
    "mls_club_season",
    metadata,
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("season_id", ForeignKey("season.id"), nullable=False),
    Column("roster_model", SmallInteger, nullable=False),  # 1 or 2
    Column("gam_cents", Integer, nullable=False),  # General Allocation Money it holds
    Column("gam_expiring_cents", Integer, nullable=False),  # Model 2's, gone at the season's end
    # The GAM its buy-downs take this season (worked out at each change; spent at the end).
    Column("gam_committed_cents", Integer, nullable=False, server_default="0"),
    Column("tam_cents", Integer, nullable=False),  # this season's Targeted Allocation Money
    Column("international_slots", SmallInteger, nullable=False),
    Column("gam_from_sales_cents", Integer, nullable=False, server_default="0"),
    Column("dp_fee_paid", SmallInteger, nullable=False, server_default="0"),
    PrimaryKeyConstraint("club_id", "season_id"),
)

# Each player's roster designation at an MLS club in a season: senior | supplemental | dp | u22 |
# homegrown | generation_adidas, and the roster he sits on (senior or supplemental).
mls_roster = Table(
    "mls_roster",
    metadata,
    Column("season_id", ForeignKey("season.id"), nullable=False),
    Column("player_id", ForeignKey("player.person_id"), nullable=False),
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("designation", Text, nullable=False),
    Column("slot", Text, nullable=False),
    PrimaryKeyConstraint("season_id", "player_id"),
    Index("ix_mls_roster_club", "club_id", "season_id"),
)

# What a player keeps from club to club in MLS: the club whose academy made him (Homegrown
# there), a green card (domestic), Generation adidas until a season, and his first MLS season.
mls_player = Table(
    "mls_player",
    metadata,
    Column("player_id", ForeignKey("player.person_id"), primary_key=True),
    Column("homegrown_club_id", ForeignKey("club.id")),
    Column("green_card", SmallInteger, nullable=False, server_default="0"),
    Column("ga_until_season", Integer),  # Generation adidas through this season (the draft)
    Column("since_season", Integer),  # his first season on an MLS roster
)

# A club's right to sign a player it hasn't signed (the SuperDraft's picks, Homegrown claims):
# kind draft | homegrown | discovery, held until a season.
mls_rights = Table(
    "mls_rights",
    metadata,
    Column("player_id", ForeignKey("player.person_id"), nullable=False),
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("kind", Text, nullable=False),
    Column("season_id", Integer, nullable=False),  # the season the right was won
    Column("until_season", Integer),
    PrimaryKeyConstraint("player_id", "kind"),
)

# Every change to a club's GAM: allocation | trade | sale | slot | spent | expired | model.
mls_gam = Table(
    "mls_gam",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("season_id", Integer, nullable=False),
    Column("date", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("amount_cents", Integer, nullable=False),
    Column("ref_id", Integer),  # a transfer, or the other club of a slot trade
    Index("ix_mls_gam_club", "club_id", "season_id"),
)


# MLS's SuperDraft (W9a B5, world/draft.py; v25): each season's picks, in order, and the user's
# own ranking of the prospects (the draft takes the best still there when the club is on the
# clock).
draft_pick = Table(
    "draft_pick",
    metadata,
    Column("season_id", ForeignKey("season.id"), nullable=False),
    Column("pick", Integer, nullable=False),  # 1, 2, ... through every round
    Column("round", Integer, nullable=False),
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("player_id", ForeignKey("person.id"), nullable=False),
    Column("signed", SmallInteger, nullable=False, server_default="0"),
    PrimaryKeyConstraint("season_id", "pick"),
)

draft_board = Table(
    "draft_board",
    metadata,
    Column("season_id", ForeignKey("season.id"), nullable=False),
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("player_id", ForeignKey("person.id"), nullable=False),
    Column("rank", Integer, nullable=False),
    PrimaryKeyConstraint("season_id", "club_id", "player_id"),
)

# --- International football (W8, world/international) ------------------------------------

national_team = Table(
    "national_team",  # a FIFA member's national team: its club row, and its Elo as it moves
    metadata,
    Column("club_id", ForeignKey("club.id"), primary_key=True),
    Column("code", Text, nullable=False, unique=True),  # FIFA's code (international/teams.yaml)
    Column("confederation", Text, nullable=False),
    Column("elo", Float, nullable=False),
)

national_pool = Table(
    "national_pool",  # made-up home-based players: no club in the game; their nation's to call up
    metadata,
    Column("player_id", ForeignKey("person.id"), primary_key=True),
    Column("code", Text, nullable=False),
    Index("ix_national_pool_code", "code"),
)

national_squad = Table(
    "national_squad",  # each national team's current squad (called up before each window)
    metadata,
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Column("player_id", ForeignKey("person.id"), nullable=False),
    PrimaryKeyConstraint("club_id", "player_id"),
    Index("ix_national_squad_player", "player_id"),
)

guest_club = Table(
    "guest_club",  # a Club World Cup guest (W10): a real club of a region with no league here
    metadata,
    Column("club_id", ForeignKey("club.id"), primary_key=True),
    Column("confederation", Text, nullable=False),
    Column("level", Float, nullable=False),  # its best XI's average overall
)

guest_player = Table(
    "guest_player",  # a guest club's made-up players (also its country's home-based players)
    metadata,
    Column("player_id", ForeignKey("person.id"), primary_key=True),
    Column("club_id", ForeignKey("club.id"), nullable=False),
    Index("ix_guest_player_club", "club_id"),
)
