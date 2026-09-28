from pathlib import Path

import pytest
from sqlalchemy import select

from footsim.persistence.database import create_database, open_database, read_meta, write_meta
from footsim.persistence.saves import SaveError, SaveManager
from footsim.persistence.schema import nation


@pytest.fixture
def base_world(tmp_path: Path) -> Path:
    path = tmp_path / "base.sqlite"
    engine = create_database(path)
    with engine.begin() as conn:
        conn.execute(nation.insert(), [{"name": "England"}])
    write_meta(engine, {"game_date": "2026-07-01"})
    engine.dispose()
    return path


def _nations(db: Path) -> list[str]:
    engine = open_database(db)
    with engine.connect() as conn:
        names = [row.name for row in conn.execute(select(nation.c.name).order_by(nation.c.name))]
    engine.dispose()
    return names


def _add_nation(db: Path, name: str) -> None:
    engine = open_database(db)
    with engine.begin() as conn:
        conn.execute(nation.insert(), [{"name": name}])
    engine.dispose()


def test_save_and_load_restore_saved_state(tmp_path: Path, base_world: Path) -> None:
    saves = SaveManager(tmp_path / "saves")
    working = saves.new_career(1, base_world)
    _add_nation(working, "Spain")
    saves.save(1)
    _add_nation(working, "France")  # unsaved progress
    saves.load(1)
    assert _nations(working) == ["England", "Spain"]


def test_meta_round_trips_and_is_summarised(tmp_path: Path, base_world: Path) -> None:
    saves = SaveManager(tmp_path / "saves")
    working = saves.new_career(2, base_world)
    engine = open_database(working)
    write_meta(engine, {"game_date": "2026-08-21"})
    assert read_meta(engine)["schema_version"] == 1
    engine.dispose()
    saves.save(2)
    summary = saves.list_slots()[1]
    assert summary.has_save and summary.meta["game_date"] == "2026-08-21"
    assert not saves.list_slots()[0].has_save


def test_corrupt_save_falls_back_to_backup(tmp_path: Path, base_world: Path) -> None:
    saves = SaveManager(tmp_path / "saves")
    working = saves.new_career(1, base_world)
    _add_nation(working, "Spain")
    saves.save(1)
    _add_nation(working, "Italy")
    saves.save(1)  # first save is now a backup
    career = saves.slot_dir(1) / "career.sqlite"
    data = bytearray(career.read_bytes())
    data[100:4000] = b"\x00" * 3900
    career.write_bytes(bytes(data))
    saves.load(1)
    assert _nations(working) == ["England", "Spain"]


def test_backups_are_rotated(tmp_path: Path, base_world: Path) -> None:
    saves = SaveManager(tmp_path / "saves", keep_backups=2)
    saves.new_career(1, base_world)
    for _ in range(5):
        saves.save(1)
    assert len(list((saves.slot_dir(1) / "backups").glob("*.sqlite"))) == 2


def test_new_career_refuses_to_overwrite(tmp_path: Path, base_world: Path) -> None:
    saves = SaveManager(tmp_path / "saves")
    saves.new_career(1, base_world)
    saves.save(1)
    with pytest.raises(SaveError, match="already has a career"):
        saves.new_career(1, base_world)
    saves.new_career(1, base_world, overwrite=True)


def test_slot_bounds(tmp_path: Path) -> None:
    with pytest.raises(SaveError):
        SaveManager(tmp_path, slots=3).slot_dir(4)
