"""One engine for every league (the calibration principles, docs/plans/continuation-plan.md).

There are no league-specific mechanics, constants or engine paths: league quality comes from the
players' ratings, then team context. The only league input ever allowed is the small, bounded
league-environment layer, and even that reaches the engine as numbers, never as a league's name.
Comments and docstrings citing real-world sources are fine; identifiers, imports, strings and
config keys or values that name a league are not.
"""

import ast
import builtins
import inspect
import re
from pathlib import Path
from typing import Any

import yaml

from footsim.core.paths import REPO_ROOT, config_dir
from footsim.match.engine.engine import MatchEngine

# League codes, with "_" and "-" counting as separators (ENG2_PO, eng1_scale, ENG-2026-27).
CODES = re.compile(r"(?<![^\W_])(ENG-?\d+|EFL)(?![^\W_])", re.IGNORECASE)
NAMES = re.compile(r"premier\s+league|league\s+(one|two)|\bchampionship\b", re.IGNORECASE)
WORDS = {"league", "leagues", "division", "divisions", "competition", "competitions"}
BUILTINS = set(dir(builtins))
ENGINE = REPO_ROOT / "backend" / "src" / "footsim" / "match" / "engine"
ENVIRONMENT_CONFIG = "environment.yaml"  # the league-environment layer, once it exists


def _words(identifier: str) -> list[str]:
    """snake_case and CamelCase identifiers split into lower-case words."""
    return [w.lower() for w in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", identifier)]


def names_a_league(identifier: str) -> bool:
    if identifier in BUILTINS:  # ZeroDivisionError and the like
        return False
    return bool(CODES.search(identifier)) or any(w in WORDS for w in _words(identifier))


def mentions_a_league(text: str) -> bool:
    """For strings: league codes and names only, so "competition for the ball" is fine."""
    return bool(CODES.search(text) or NAMES.search(text))


def _docstrings(tree: ast.Module) -> set[int]:
    owners: list[ast.AST] = [tree, *(n for n in ast.walk(tree) if isinstance(
        n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef))]
    found = set()
    for owner in owners:
        body = getattr(owner, "body", [])
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            found.add(id(body[0].value))
    return found


def _hits(node: ast.AST, docstrings: set[int]) -> list[str]:
    identifiers: list[str] = []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value] if id(node) not in docstrings and mentions_a_league(node.value) else []
    if isinstance(node, ast.Name):
        identifiers = [node.id]
    elif isinstance(node, ast.Attribute):
        identifiers = [node.attr]
    elif isinstance(node, ast.arg) or isinstance(node, ast.keyword) and node.arg:
        identifiers = [node.arg]
    elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        identifiers = [node.name]
    elif isinstance(node, ast.alias):
        identifiers = [*node.name.split("."), *([node.asname] if node.asname else [])]
    elif isinstance(node, ast.ImportFrom) and node.module:
        identifiers = node.module.split(".")
    return [name for name in identifiers if names_a_league(name)]


def _walk_yaml(value: Any, where: str) -> list[str]:
    if isinstance(value, dict):
        return [hit for k, v in value.items() for hit in
                ([f"{where}: key {k}"] if names_a_league(str(k)) else [])
                + _walk_yaml(v, f"{where}.{k}")]
    if isinstance(value, list):
        return [hit for i, v in enumerate(value) for hit in _walk_yaml(v, f"{where}[{i}]")]
    if isinstance(value, str) and mentions_a_league(value):
        return [f"{where}: {value!r}"]
    return []


def test_the_guard_itself() -> None:
    for bad in ("league_level", "ENG2_PO", "eng1_scale", "EFL_BIAS", "competition", "Division"):
        assert names_a_league(bad), bad
    for fine in ("ZeroDivisionError", "colleague", "engine", "eng", "tackle_ready"):
        assert not names_a_league(fine), fine
    assert mentions_a_league("ENG-2026-27") and mentions_a_league("Premier League")
    assert not mentions_a_league("competition for the ball")


def test_engine_code_names_no_league() -> None:
    found = []
    for path in sorted(ENGINE.glob("*.py")):
        tree = ast.parse(path.read_text("utf-8"))
        docstrings = _docstrings(tree)
        for node in ast.walk(tree):
            found += [f"{path.name}:{getattr(node, 'lineno', '?')}: {hit!r}"
                      for hit in _hits(node, docstrings)]
    assert not found, found


def test_match_config_names_no_league() -> None:
    found = []
    for path in sorted(Path(config_dir(), "match").rglob("*.yaml")):
        if path.name != ENVIRONMENT_CONFIG:
            found += _walk_yaml(yaml.safe_load(path.read_text("utf-8")), path.name)
    assert not found, found


def test_the_engine_takes_no_league() -> None:
    params = inspect.signature(MatchEngine.__init__).parameters
    assert not [p for p in params if names_a_league(p)]
