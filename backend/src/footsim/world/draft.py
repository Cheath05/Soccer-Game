"""MLS's SuperDraft (W9a B5): in January the MLS clubs pick, round after round, from the college
prospects of the NCAA season just finished (world/college: ``draft_pool``).

- **The order:** the reverse of last season's Supporters' Shield table, adjusted for the
  play-offs: the clubs that missed them first, then those out in each round, the MLS Cup winners
  last. In a career's first season (no last season) the table so far stands in.
- **A pick:** a club's value of a prospect is his overall plus a share of the potential above it,
  as its scouts see it (each club's own error), plus a bonus for a position group it is short
  in. The user's club takes the best still there from the user's own ranking (the draft board),
  and its scouts' choice when the board runs out.
- **Signing:** a pick turns pro and his club holds his MLS rights (``mls_rights``, kind draft);
  the club signs him at once if MLS's rules allow (the user's club always tries; AI clubs for
  their early rounds), at the minimum, Generation adidas picks on the supplemental roster for a
  few seasons. An unsigned pick can be signed later (``sign_pick``) while the rights last; no
  other MLS club may sign him meanwhile.

Deterministic: the noise is seeded by the career, the season, the club and the player."""

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Connection, select, text

from footsim.core.rng import derive_rng
from footsim.defs.mls import SuperDraftDef
from footsim.importers.generate import age_on
from footsim.persistence.schema import draft_board, draft_pick, mls_rights
from footsim.world.college import DraftProspect, draft_pool, turn_pro
from footsim.world.context import World
from footsim.world.meta import CareerMeta
from footsim.world.mls import figures, mls_club_ids
from footsim.world.squads import club_name
from footsim.world.transfers import Move, MoveRefused, complete_move, senior_squad

# The draft's position needs by line (the eight position groups into four).
LINE = {"GK": "GK", "CB": "DEF", "FB": "DEF", "DM": "MID", "CM": "MID", "AM": "MID", "W": "FWD",
        "ST": "FWD"}
WEEKS = 52


@dataclass(frozen=True)
class Pick:
    pick: int
    round: int
    club_id: int
    player_id: int | None  # None: still to be made


def rules(world: World) -> SuperDraftDef:
    return world.defs.mls.superdraft


def draft_date(world: World, conn: Connection, season_id: int) -> date:
    """The day of a season's draft: its January (the year after the season starts)."""
    start = date.fromisoformat(str(conn.execute(text(
        "SELECT start_date FROM season WHERE id = :s"), {"s": season_id}).scalar_one()))
    month, day = rules(world).month_day()
    return date(start.year + (1 if month < start.month else 0), month, day)


def _league(conn: Connection, world: World) -> tuple[int, Any] | None:
    key = world.defs.mls.league
    league = world.defs.leagues.get(key)
    cid = conn.execute(text("SELECT id FROM competition WHERE key = :k"), {"k": key}).scalar()
    return (int(cid), league) if cid is not None and league is not None else None


def draft_order(conn: Connection, world: World, meta: CareerMeta, season_id: int) -> list[int]:
    """The first round's order (every round's): the clubs that did worst last season first."""
    clubs = sorted(mls_club_ids(conn, world, season_id))
    found = _league(conn, world)
    if found is None:
        return clubs
    comp, league = found
    finals = {int(r.club_id): int(r.position) for r in conn.execute(text(
        "SELECT club_id, position FROM league_final WHERE competition_id = :c "
        "AND season_id = :s"), {"c": comp, "s": season_id - 1})}
    reached: dict[int, int] = {}  # the play-off round a club went out in (the winners: beyond)
    playoff = league.title_playoff
    if finals and playoff is not None:
        for t in conn.execute(text(
                "SELECT round, club_a_id, club_b_id, winner_club_id FROM playoff_tie "
                "WHERE season_id = :s AND playoff_key = :k"),
                {"s": season_id - 1, "k": playoff.key}):
            for club in (t.club_a_id, t.club_b_id):
                if club is None:
                    continue
                won = t.winner_club_id == club
                stage = t.round + (2 if won and t.round == len(playoff.rounds) - 1 else 1)
                reached[int(club)] = max(reached.get(int(club), 0), stage)
    if not finals:  # the career's first season: this season's table so far
        from footsim.world.season import standings

        finals = {r.club_id: r.position for r in standings(conn, world, meta, comp, season_id)}
    worst = max(finals.values(), default=0) + 1
    return sorted(clubs, key=lambda c: (reached.get(c, 0), -finals.get(c, worst), c))


def picks(conn: Connection, world: World, meta: CareerMeta, season_id: int) -> list[Pick]:
    """Every pick of a season's draft: those made, and (before the draft) those to come."""
    made = {int(r.pick): r for r in conn.execute(select(draft_pick).where(
        draft_pick.c.season_id == season_id))}
    if made:
        return [Pick(int(r.pick), int(r.round), int(r.club_id), int(r.player_id))
                for _, r in sorted(made.items())]
    order = draft_order(conn, world, meta, season_id)
    return [Pick(n * len(order) + k + 1, n + 1, club, None)
            for n in range(rules(world).rounds) for k, club in enumerate(order)]


def scouted_potential(meta: CareerMeta, season_id: int, club_id: int,
                      prospect: DraftProspect, sd: float) -> float:
    """A prospect's potential as a club's scouts see it (their own, steady error)."""
    rng = derive_rng(meta.seed, "draft-scouting", season_id, club_id, prospect.player_id)
    return max(float(prospect.overall), prospect.potential + float(rng.normal(0.0, sd)))


def _needs(conn: Connection, world: World, club_id: int, day: date) -> set[str]:
    """The lines a club is short in, by its senior players' positions."""
    targets = rules(world).group_targets
    ids = senior_squad(conn, world, club_id, day)
    have: Counter[str] = Counter()
    for pid in ids:
        pos = conn.execute(text("SELECT position FROM player_position WHERE player_id = :p "
                                "ORDER BY familiarity DESC LIMIT 1"), {"p": pid}).scalar()
        if pos in world.defs.positions:
            have[LINE[world.defs.positions[pos].group.value]] += 1
    return {line for line, want in targets.items() if have[line] < want}


def value(world: World, meta: CareerMeta, season_id: int, club_id: int,
          prospect: DraftProspect, needs: set[str]) -> float:
    """What a prospect is worth to a club in the draft."""
    r = rules(world)
    seen = scouted_potential(meta, season_id, club_id, prospect, r.scouting_sd)
    line = LINE[world.defs.positions[prospect.position].group.value] if (
        prospect.position in world.defs.positions) else ""
    return (prospect.overall + r.potential_weight * (seen - prospect.overall)
            + (r.need_bonus if line in needs else 0.0))


def board(conn: Connection, season_id: int, club_id: int) -> list[int]:
    """A club's own ranking of the prospects (the user's draft board), best first."""
    return [int(r.player_id) for r in conn.execute(select(draft_board).where(
        draft_board.c.season_id == season_id, draft_board.c.club_id == club_id)
        .order_by(draft_board.c.rank))]


def set_board(conn: Connection, world: World, meta: CareerMeta, club_id: int,
              player_ids: list[int]) -> None:
    """The user's ranking for this season's draft (prospects only; before the draft)."""
    if conn.execute(select(draft_pick.c.pick).where(
            draft_pick.c.season_id == meta.season_id)).first() is not None:
        raise ValueError("This season's draft has been made.")
    pool = {p.player_id for p in draft_pool(conn, world, meta, meta.season_id)}
    unknown = [pid for pid in player_ids if pid not in pool]
    if unknown or len(set(player_ids)) != len(player_ids):
        raise ValueError("Rank each prospect once, from this season's pool.")
    conn.execute(draft_board.delete().where(draft_board.c.season_id == meta.season_id,
                                            draft_board.c.club_id == club_id))
    if player_ids:
        conn.execute(draft_board.insert(), [
            {"season_id": meta.season_id, "club_id": club_id, "player_id": pid, "rank": k}
            for k, pid in enumerate(player_ids, start=1)])


def _contract(world: World, meta: CareerMeta, conn: Connection, prospect_ga: bool, round_: int,
              age: int) -> tuple[int, date]:
    """A pick's weekly wage (euro cents) and contract end."""
    r, fig = rules(world), figures(world)
    senior = round_ == 1 or prospect_ga or age > world.defs.mls.reserve_max_age
    yearly = fig.senior_minimum if senior else fig.reserve_minimum
    end = date.fromisoformat(str(conn.execute(text(
        "SELECT end_date FROM season WHERE id = :s"), {"s": meta.season_id}).scalar_one()))
    years = r.ga_contract_years if prospect_ga else r.contract_years
    return -(-yearly // WEEKS), date(end.year + years - 1, end.month, end.day)


def _sign(conn: Connection, world: World, meta: CareerMeta, club_id: int, player_id: int,
          round_: int, day: date, by_user: bool) -> str | None:
    """Sign a pick for his club; the reason he can't be, or None."""
    row = conn.execute(text(
        "SELECT p.birth_date, cp.ga FROM person p LEFT JOIN college_player cp "
        "ON cp.player_id = p.id WHERE p.id = :p"), {"p": player_id}).one()
    ga = bool(row.ga)
    age = age_on(date.fromisoformat(row.birth_date), day)
    wage, end = _contract(world, meta, conn, ga, round_, age)
    try:
        complete_move(conn, world, meta, Move(player_id, club_id, 0, wage, end, by_user=by_user),
                      day)
    except MoveRefused as refused:
        return str(refused)
    conn.execute(text("UPDATE draft_pick SET signed = 1 WHERE season_id = :s AND player_id = :p"),
                 {"s": meta.season_id, "p": player_id})
    conn.execute(mls_rights.delete().where(mls_rights.c.player_id == player_id,
                                           mls_rights.c.kind == "draft"))
    return None


def _mark_ga(conn: Connection, world: World, meta: CareerMeta, player_id: int) -> None:
    """A Generation adidas pick sits on the supplemental roster for a few seasons."""
    until = meta.season_id + rules(world).ga_seasons - 1
    conn.execute(text(
        "INSERT INTO mls_player (player_id, green_card, ga_until_season) VALUES (:p, 0, :u) "
        "ON CONFLICT(player_id) DO UPDATE SET ga_until_season = :u"),
        {"p": player_id, "u": until})


def run_draft(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """The season's draft, made today (once). Returns news."""
    if conn.execute(select(draft_pick.c.pick).where(
            draft_pick.c.season_id == meta.season_id)).first() is not None:
        return []
    pool = {p.player_id: p for p in draft_pool(conn, world, meta, meta.season_id)}
    order = picks(conn, world, meta, meta.season_id)
    if not pool or not order:
        return []
    needs = {c: _needs(conn, world, c, day) for c in {p.club_id for p in order}}
    user = meta.user_club_id
    mine: list[str] = []
    first_pick = ""
    for p in order:
        if not pool:
            break
        ranked = board(conn, meta.season_id, p.club_id) if p.club_id == user else []
        chosen = next((pid for pid in ranked if pid in pool), None)
        if chosen is None:
            chosen = max(pool, key=lambda pid: (value(
                world, meta, meta.season_id, p.club_id, pool[pid], needs[p.club_id]), -pid))
        prospect = pool.pop(chosen)
        turn_pro(conn, meta, chosen, day)
        if prospect.ga:
            _mark_ga(conn, world, meta, chosen)
        conn.execute(draft_pick.insert().values(
            season_id=meta.season_id, pick=p.pick, round=p.round, club_id=p.club_id,
            player_id=chosen, signed=0))
        conn.execute(text(
            "INSERT OR REPLACE INTO mls_rights (player_id, club_id, kind, season_id, "
            "until_season) VALUES (:p, :c, 'draft', :s, :u)"),
            {"p": chosen, "c": p.club_id, "s": meta.season_id,
             "u": meta.season_id + rules(world).rights_seasons})
        if p.pick == 1:
            first_pick = f"{club_name(conn, p.club_id)} take {prospect.name} ({prospect.college})"
        if p.club_id == user or p.round <= rules(world).ai_sign_rounds:
            refused = _sign(conn, world, meta, p.club_id, chosen, p.round, day,
                            by_user=p.club_id == user)
            if p.club_id == user:
                mine.append(f"{prospect.name} ({prospect.position}, {prospect.college}, pick "
                            f"{p.pick})" + ("" if refused is None else
                                            f": unsigned ({refused.rstrip('.')})"))
    news = [f"The MLS SuperDraft: {first_pick} with the first pick."] if first_pick else []
    if mine:
        news.append("Your SuperDraft picks: " + "; ".join(mine) + ". Unsigned picks can be "
                    "signed from the Draft page while you hold their rights.")
    return news


def sign_pick(conn: Connection, world: World, meta: CareerMeta, player_id: int,
              day: date) -> None:
    """Sign one of the user's unsigned picks (MoveRefused with the reason if he can't be)."""
    row = conn.execute(text(
        "SELECT d.round FROM draft_pick d JOIN mls_rights r ON r.player_id = d.player_id "
        "AND r.kind = 'draft' AND r.club_id = d.club_id WHERE d.player_id = :p "
        "AND d.club_id = :c AND d.signed = 0 AND r.until_season >= :s"),
        {"p": player_id, "c": meta.user_club_id, "s": meta.season_id}).first()
    if row is None or meta.user_club_id is None:
        raise MoveRefused("He isn't one of your unsigned draft picks.")
    refused = _sign(conn, world, meta, meta.user_club_id, player_id, int(row.round), day, True)
    if refused is not None:
        raise MoveRefused(refused)


def draft_day(conn: Connection, world: World, meta: CareerMeta, day: date) -> list[str]:
    """The day's draft business: the reminder to the user's MLS club, and the draft itself."""
    if world.defs.mls.league not in world.defs.leagues:
        return []
    when = draft_date(world, conn, meta.season_id)
    user = meta.user_club_id
    if day == when:
        return run_draft(conn, world, meta, day)
    if (day == when - timedelta(days=rules(world).reminder_days) and user is not None
            and user in mls_club_ids(conn, world, meta.season_id)):
        return [f"The MLS SuperDraft is on {when.day} {when.strftime('%B')}: rank the college "
                "prospects on the Draft page, or your scouts will choose."]
    return []
