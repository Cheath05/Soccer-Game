"""Repository locations. Override with environment variables for tests or mods."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]


def config_dir() -> Path:
    return Path(os.environ.get("FOOTSIM_CONFIG_DIR", REPO_ROOT / "data" / "config"))


def data_dir() -> Path:
    return Path(os.environ.get("FOOTSIM_DATA_DIR", REPO_ROOT / "data"))


def saves_dir() -> Path:
    return Path(os.environ.get("FOOTSIM_SAVES_DIR", REPO_ROOT / "saves"))
