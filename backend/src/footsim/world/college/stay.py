"""Draft watch and asking a player to stay (22 Nov; ``draft`` in data/config/college/rules.yaml).

After the College Cup the best underclassmen declare early for MLS's SuperDraft
(world/college/draft.py ``declare_prospects``: the ``underclassmen`` best by potential, then
overall, with at least ``min_potential``). The draft watch runs the same order all season, so a
college coach can plan: those who would declare if it were today are "likely" to leave early,
the next ``watch_extra`` "possible". He hears of his own on ``watch_news``.

He may ask each of them to stay, once a season: before the declarations (if he agrees, he won't
declare this season) or after, until the draft (if he agrees, he withdraws from the pool). His
chance (``stay_pitch``) grows with his share of the team's minutes and the program's prestige,
and shrinks the bigger a prospect he is, and once he has declared. The answer is drawn from the
career's seed, so asking again can't change it. An OP player never declares (god_player.py)."""

from dataclasses import dataclass
from datetime import date

import numpy as np
from sqlalchemy import Connection, text

from footsim.core.rng import derive_rng
from footsim.defs.college import on
from footsim.domain.attributes import ATTRIBUTES
from footsim.world.college.common import ENROLLED, PROSPECT
from footsim.world.context import World
from footsim.world.meta import CareerMeta, write_meta
from footsim.world.squads import display_name

LIKELY = "likely"
POSSIBLE = "possible"


class StayRefused(ValueError):
    """Why the coach can't ask him (shown to the user)."""


def staying(meta: CareerMeta, season_id: int) -> set[int]:
    """The players who agreed this season not to leave early."""
    return {p for p, (s, stays) in meta.stay_pitches.items() if s == season_id and stays}


def _overalls(conn: Connection, world: World, ids: list[int]) -> dict[int, float]:
    """Each player's overall at his best position."""
    if not ids:
        return {}
    marks = ",".join(str(i) for i in ids)
    rows = conn.execute(text(
        f"SELECT a.*, (SELECT position FROM player_position pp WHERE pp.player_id = a.player_id "
        f"ORDER BY familiarity DESC, position LIMIT 1) AS position FROM player_attr a "
        f"WHERE a.player_id IN ({marks}) ORDER BY a.player_id")).all()
    groups = world.model.group_overalls(
        np.array([[getattr(r, a) for a in ATTRIBUTES] for r in rows], dtype=float))
    out = {}
    for i, r in enumerate(rows):
        position = str(r.position or "CM")
        group = world.defs.positions[position].group if position in world.defs.positions \
            else world.defs.positions["CM"].group
        out[int(r.player_id)] = float(groups[group][i])
    return out


def draft_watch(conn: Connection, world: World, meta: CareerMeta) -> dict[int, str]:
    """Every D-I underclassman who would declare early if it were today (``likely``) or is next
    in line (``possible``): the declarations' order, leaving out OP players and those who agreed
    to stay."""
    rules = world.defs.college.rules.draft
    rows = conn.execute(text(
        "SELECT cp.player_id, pl.pa_hidden FROM college_player cp "
        "JOIN player pl ON pl.person_id = cp.player_id "
        "WHERE cp.status = :e AND cp.class_year < 4 AND pl.pa_hidden >= :least"),
        {"e": ENROLLED, "least": rules.min_potential}).all()
    skip = set(meta.god_players) | staying(meta, meta.season_id)
    rows = [r for r in rows if int(r.player_id) not in skip]
    overall = _overalls(conn, world, [int(r.player_id) for r in rows])
    order = sorted(rows, key=lambda r: (-int(r.pa_hidden), -round(overall[int(r.player_id)]),
                                        int(r.player_id)))
    out = {}
    for k, r in enumerate(order[:rules.underclassmen + rules.watch_extra]):
        out[int(r.player_id)] = LIKELY if k < rules.underclassmen else POSSIBLE
    return out


@dataclass(frozen=True)
class Pitch:
    """What the coach knows before asking: whether he can, and the chance."""

    can_ask: bool
    chance: float
    asked: str | None  # "stays" or "leaving" once asked this season


def _club_minutes_share(conn: Connection, club_id: int, player_id: int, season_id: int) -> float:
    games: int = conn.execute(text(
        "SELECT COUNT(*) FROM fixture WHERE season_id = :s AND status = 'played' "
        "AND (home_club_id = :c OR away_club_id = :c)"), {"s": season_id, "c": club_id}
    ).scalar_one()
    if not games:
        return 0.0
    minutes: float = conn.execute(text(
        "SELECT COALESCE(SUM(pm.minutes), 0) FROM player_match pm JOIN fixture f "
        "ON f.id = pm.fixture_id WHERE pm.player_id = :p AND pm.club_id = :c "
        "AND f.season_id = :s"), {"p": player_id, "c": club_id, "s": season_id}).scalar_one()
    return min(1.0, float(minutes) / (90.0 * int(games)))


def pitch(conn: Connection, world: World, meta: CareerMeta, player_id: int,
          risk: str | None = None) -> Pitch:
    """Whether the coach can ask ``player_id`` to stay this season, and the chance he agrees.
    ``risk`` is his draft watch, when the caller has it."""
    from footsim.world.college.program import facilities_bonus

    rules = world.defs.college.rules.draft
    spec = rules.stay_pitch
    row = conn.execute(text(
        "SELECT cp.club_id, cp.status, cp.class_year, cp.declared_season, pl.pa_hidden, "
        "ct.prestige FROM college_player cp JOIN player pl ON pl.person_id = cp.player_id "
        "JOIN college_team ct ON ct.club_id = cp.club_id WHERE cp.player_id = :p"),
        {"p": player_id}).first()
    asked = meta.stay_pitches.get(player_id)
    answer = None
    if asked is not None and asked[0] == meta.season_id:
        answer = "stays" if asked[1] else "leaving"
    if spec is None or row is None or row.club_id != meta.user_club_id or row.class_year >= 4:
        return Pitch(False, 0.0, answer)
    declared = row.status == PROSPECT and row.declared_season == meta.season_id
    if risk is None and not declared:
        risk = draft_watch(conn, world, meta).get(player_id)
    if not declared and risk is None:
        return Pitch(False, 0.0, answer)
    prestige = float(row.prestige or 0.0) + facilities_bonus(conn, world, int(row.club_id))
    chance = (spec.base
              + spec.playing_time * _club_minutes_share(conn, int(row.club_id), player_id,
                                                        meta.season_id)
              + spec.prestige * (prestige - spec.prestige_par) / 10.0
              - spec.talent * max(0, int(row.pa_hidden) - rules.min_potential)
              - (spec.declared if declared else 0.0))
    chance = min(spec.most, max(spec.least, chance))
    return Pitch(answer is None, round(chance, 2), answer)


def ask_to_stay(conn: Connection, world: World, meta: CareerMeta, player_id: int) -> bool:
    """Ask him to stay; True if he agrees. Before the declarations he then won't declare this
    season; after, he withdraws from the draft pool. Raises StayRefused."""
    p = pitch(conn, world, meta, player_id)
    if p.asked is not None:
        raise StayRefused("You've asked him already this season.")
    if not p.can_ask:
        raise StayRefused("Only your underclassmen who may leave early for the draft (or who "
                          "have declared) can be asked to stay.")
    roll = float(derive_rng(meta.seed, "stay-pitch", player_id, meta.season_id).random())
    stays = roll < p.chance
    meta.stay_pitches[player_id] = (meta.season_id, int(stays))
    if stays:
        conn.execute(text(
            "UPDATE college_player SET status = :e, declared_season = NULL, ga = 0 "
            "WHERE player_id = :p AND status = :prospect"),
            {"e": ENROLLED, "p": player_id, "prospect": PROSPECT})
    write_meta(conn, meta)
    return stays


def watch_news(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """On ``watch_news``, the coach's players who may leave early. Returns news."""
    from footsim.world.college.common import is_college_club
    from footsim.world.college.season import _season_start

    rules = world.defs.college.rules.draft
    user = meta.user_club_id
    if user is None or not is_college_club(conn, user) or day != on(
            rules.watch_news, _season_start(conn, meta.season_id)):
        return []
    watch = draft_watch(conn, world, meta)
    news = []
    for r in conn.execute(text(
            "SELECT cp.player_id, cp.class_year, p.first_name, p.last_name, p.known_as "
            "FROM college_player cp JOIN person p ON p.id = cp.player_id "
            "WHERE cp.club_id = :c ORDER BY cp.player_id"), {"c": user}):
        risk = watch.get(int(r.player_id))
        if risk is None:
            continue
        name = display_name(r.first_name, r.last_name, r.known_as)
        how = "is likely to" if risk == LIKELY else "may"
        news.append(f"Draft watch: your player {name} {how} leave early for the MLS SuperDraft "
                    "after the College Cup. Ask him to stay on his page.")
    return news
