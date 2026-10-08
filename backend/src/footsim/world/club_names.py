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
