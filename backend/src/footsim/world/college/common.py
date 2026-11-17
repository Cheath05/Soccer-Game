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
IN_COLLEGE_SQL = "SELECT player_id FROM college_player WHERE status IN ('enrolled', 'prospect')"
COLLEGE_CLUBS_SQL = "SELECT club_id FROM college_team"

REGULAR = "college"  # the regular season's fixtures' stage
NCAA = "NCAA"  # the NCAA tournament's stage and event
CONFERENCE_PREFIX = "CT:"  # a conference tournament's stage and event: CT:<conference key>


def conference_event(conference: str) -> str:
    return f"{CONFERENCE_PREFIX}{conference}"


def is_college_stage(stage: str) -> bool:
    return stage in (REGULAR, NCAA) or stage.startswith(CONFERENCE_PREFIX)


def in_college(conn: Connection, player_id: int) -> bool:
    """Whether the player is still a college player (enrolled, or declared and not yet pro)."""
    return conn.execute(text("SELECT 1 FROM college_player WHERE player_id = :p "
                             "AND status IN ('enrolled', 'prospect')"),
                        {"p": player_id}).first() is not None


def college_club_ids(conn: Connection) -> set[int]:
    return {int(r.club_id) for r in conn.execute(text(COLLEGE_CLUBS_SQL))}
