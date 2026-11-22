"""What the rest of the game needs to keep college soccer apart from the professional game.

College players hold a contract of kind ``college`` at their program (no wage), so squads and
matches see them like anyone else's players. They stay outside the professional systems while
enrolled or declared for the draft: the market, loans, renewals and wages, youth intakes, squad
trims and finances. College clubs have no ledger, no league and a fixed reputation."""

from sqlalchemy import Connection, text

COLLEGE_CONTRACT = "college"
ENROLLED = "enrolled"
PROSPECT = "prospect"
PRO = "pro"
UNDRAFTED = "undrafted"
IN_COLLEGE = (ENROLLED, PROSPECT)  # outside the professional game

# SQL for the players still in college and the college clubs, for the queries that leave them
# out (both tables exist from schema v24; empty in a world without the college game).
# D-II and D-III (W9e, v30) are college too: their players and programs stay out of the
# professional game alike.
IN_COLLEGE_SQL = ("SELECT player_id FROM college_player WHERE status IN ('enrolled', 'prospect') "
                  "UNION SELECT player_id FROM lower_player")
COLLEGE_CLUBS_SQL = "SELECT club_id FROM college_team UNION SELECT club_id FROM lower_team"

REGULAR = "college"  # the regular season's fixtures' stage
NCAA = "NCAA"  # the NCAA tournament's stage and event
CONFERENCE_PREFIX = "CT:"  # a conference tournament's stage and event: CT:<conference key>


def conference_event(conference: str) -> str:
    return f"{CONFERENCE_PREFIX}{conference}"


LOWER_PREFIX = "LOWER"  # a D-II/D-III national tournament's stage and event: LOWER2, LOWER3 (W9e)
LOWER_TYPE = "college_lower"  # the competition type of NCAA Divisions II and III
LOWER_REGULAR = "lower"  # a D-II/D-III regular-season fixture's stage (apart from D-I's)
ALL_DIVISION = "ADT"  # the All-Division Tournament's stage and event (22 Nov)
ALL_TYPE = "college_all"  # its competition's type


def is_lower_stage(stage: str) -> bool:
    return stage.startswith(LOWER_PREFIX)


def is_college_stage(stage: str) -> bool:
    return stage in (REGULAR, NCAA) or stage.startswith(CONFERENCE_PREFIX)


def in_college(conn: Connection, player_id: int) -> bool:
    """Whether the player is still a college player (enrolled, or declared and not yet pro; or
    at a D-II/D-III school)."""
    return conn.execute(text(f"SELECT 1 FROM ({IN_COLLEGE_SQL}) WHERE player_id = :p"),
                        {"p": player_id}).first() is not None


def college_club_ids(conn: Connection) -> set[int]:
    return {int(r.club_id) for r in conn.execute(text(COLLEGE_CLUBS_SQL))}


def college_club_id(conn: Connection, program: str) -> int:
    """The club of the D-I program named ``program`` ("Indiana Hoosiers"). Raises KeyError."""
    found = conn.execute(text("SELECT c.id FROM club c WHERE c.name = :n AND c.id IN "
                              "(SELECT club_id FROM college_team)"), {"n": program}).scalar()
    if found is None:
        raise KeyError(program)
    return int(found)


def is_college_club(conn: Connection, club_id: int | None) -> bool:
    return club_id is not None and conn.execute(text(
        "SELECT 1 FROM college_team WHERE club_id = :c"), {"c": club_id}).first() is not None
