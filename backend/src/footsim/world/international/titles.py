"""World titles for a club's trophy cabinet (api/honours.py): the World Cups a national team has
won and the Club World Cups a club has, each by the year of its final. They are read from the
finals' fixtures (``WCF:F`` / ``WCF:<year>:F``, ``CWC:F``), not from ``league_title``, which
holds leagues' titles."""

from dataclasses import dataclass

from sqlalchemy import Connection, text

from footsim.world.international.finals import _winner

WORLD_CUP = ("WC", "FIFA World Cup")  # (key, name) in the cabinet
CLUB_WORLD_CUP = ("CWC", "FIFA Club World Cup")


@dataclass(frozen=True)
class WorldTitle:
    key: str
    name: str
    year: str


def world_titles(conn: Connection, club_id: int) -> list[WorldTitle]:
    """The world titles ``club_id`` has won, oldest first."""
    rows = conn.execute(text(
        "SELECT * FROM fixture WHERE status = 'played' "
        "AND (home_club_id = :c OR away_club_id = :c) "
        "AND (stage IN (:wc, :cwc) OR stage GLOB :later) ORDER BY date"),
        {"c": club_id, "wc": "WCF:F", "cwc": "CWC:F", "later": "WCF:[0-9]*:F"}).all()
    found = []
    for f in rows:
        if _winner(f) == club_id:
            key, name = CLUB_WORLD_CUP if f.stage.startswith("CWC:") else WORLD_CUP
            found.append(WorldTitle(key, name, str(f.date)[:4]))
    return found
