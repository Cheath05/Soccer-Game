"""Reads players from the transfermarkt-datasets DuckDB snapshot (CC0)."""

from datetime import date, datetime
from pathlib import Path

from footsim.importers.records import TmPlayer

_QUERY = """
SELECT player_id, name, first_name, last_name, date_of_birth, country_of_citizenship,
       height_in_cm, foot, position, sub_position, contract_expiration_date,
       market_value_in_eur, current_club_name, city_of_birth
FROM players
WHERE date_of_birth IS NOT NULL
"""


def _as_date(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    return value.date() if isinstance(value, datetime) else value


def load_players(db_path: Path) -> list[TmPlayer]:
    import duckdb  # data-pipeline dependency, only needed when building worlds

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(_QUERY).fetchall()
    finally:
        con.close()
    players = []
    for row in rows:
        birth = _as_date(row[4])
        if birth is None:
            continue
        players.append(
            TmPlayer(
                tm_id=int(row[0]),
                name=row[1] or "",
                first_name=row[2] or "",
                last_name=row[3] or "",
                birth_date=birth,
                citizenship=row[5],
                height_cm=int(row[6]) if row[6] else None,
                foot=row[7],
                position=row[8],
                sub_position=row[9],
                contract_expiry=_as_date(row[10]),
                market_value_eur=int(row[11]) if row[11] else None,
                club_name=row[12],
                city_of_birth=row[13],
            )
        )
    return players
