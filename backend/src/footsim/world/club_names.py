"""Real names for clubs the source data lists under made-up ones (world/club_names.yaml)."""

from pathlib import Path

import yaml
from sqlalchemy import Connection, text

from footsim.core.paths import config_dir


def load_club_names(root: Path | None = None) -> dict[str, dict[str, str]]:
    """{nation name: {name in the data: real name}}."""
    path = (root or config_dir()) / "world" / "club_names.yaml"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return {str(nation): {str(old): str(new) for old, new in names.items()}
            for nation, names in raw.items()}


def apply_club_names(conn: Connection, names: dict[str, dict[str, str]] | None = None) -> int:
    """Rename clubs by their old name, within the nation. Idempotent; also keeps the career's
    ``club_name`` meta (the user's club) in step. Returns the number of clubs renamed."""
    import json

    names = load_club_names() if names is None else names
    renamed = 0
    for nation, mapping in names.items():
        for old, new in mapping.items():
            result = conn.execute(text(
                "UPDATE club SET name = :new WHERE name = :old AND nation_id = "
                "(SELECT id FROM nation WHERE name = :nation)"),
                {"new": new, "old": old, "nation": nation})
            renamed += result.rowcount or 0
            row = conn.execute(text("SELECT value FROM game_meta WHERE key = 'club_name'")).first()
            if row is not None and json.loads(row[0]) == old:
                conn.execute(text("UPDATE game_meta SET value = :v WHERE key = 'club_name'"),
                             {"v": json.dumps(new)})
    return renamed


def load_club_nations(root: Path | None = None) -> dict[str, dict[str, str]]:
    """{source league: {club name: nation code}}: clubs of another country than their league's
    (world/club_nations.yaml; MLS's Canadian clubs)."""
    path = (root or config_dir()) / "world" / "club_nations.yaml"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return {str(league): {str(name): str(code) for name, code in clubs.items()}
            for league, clubs in raw.items()}


def apply_club_nations(conn: Connection, nations: dict[str, dict[str, str]] | None = None
                       ) -> int:
    """Give the listed clubs their own nation, by source league and name. Idempotent. Returns
    the number of clubs changed."""
    nations = load_club_nations() if nations is None else nations
    changed = 0
    for league, clubs in nations.items():
        for name, code in clubs.items():
            result = conn.execute(text(
                "UPDATE club SET nation_id = (SELECT id FROM nation WHERE code = :code) "
                "WHERE source_league = :league AND name = :name AND (nation_id IS NULL OR "
                "nation_id != (SELECT id FROM nation WHERE code = :code))"),
                {"code": code, "league": league, "name": name})
            changed += result.rowcount or 0
    return changed
