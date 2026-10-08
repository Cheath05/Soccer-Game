"""Sim to date: the career moves on to a chosen date in the background, playing the user's
matches as Instant would, while the viewer shows progress and can stop it.

One job at a time. Each step (a match, or the days up to the next one) holds the career's
write lock only for itself, so the rest of the game stays readable meanwhile, and the career
is autosaved after each of the user's matches and at the end. Loading or starting another
career abandons the job (``CareerSession.generation``).
"""

import threading
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import Connection, Row, or_, select

from footsim.api.schemas import SeasonFinalOut, SimIn, SimResultOut, SimStatusOut, SimTargetOut
from footsim.api.season_review import season_final
from footsim.api.session import CareerSession
from footsim.persistence.schema import club, competition, fixture
from footsim.world.career import sim_step
from footsim.world.context import get_world
from footsim.world.meta import read_meta

router = APIRouter(prefix="/api")

MAX_DAYS = 400  # the furthest a single sim may go


@dataclass
class SimJob:
    start: date
    until: date
    generation: int
    day: date
    results: list[SimResultOut] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    stop: str | None = None  # date | season_end | offer | cancelled | abandoned | error
    error: str | None = None
    season_final: SeasonFinalOut | None = None
    cancel: threading.Event = field(default_factory=threading.Event)

    @property
    def running(self) -> bool:
        return self.stop is None

    def status(self) -> SimStatusOut:
        return SimStatusOut(running=self.running, start=self.start.isoformat(),
                            until=self.until.isoformat(), date=self.day.isoformat(),
                            results=list(self.results), messages=list(self.messages),
                            stop=self.stop, error=self.error, season_final=self.season_final)


def running(session: CareerSession) -> bool:
    job: SimJob | None = session.sim
    return job is not None and job.running


def _session(request: Request) -> CareerSession:
    session: CareerSession = request.app.state.session
    return session


def _result(session: CareerSession, fixture_id: int, user: int) -> SimResultOut:
    with session.read() as conn:
        fx = conn.execute(select(fixture).where(fixture.c.id == fixture_id)).one()
        names: dict[int, str] = {row.id: row.name for row in conn.execute(
            select(club.c.id, club.c.name).where(club.c.id.in_([fx.home_club_id,
                                                                 fx.away_club_id])))}
        comp_name: str = conn.execute(select(competition.c.name).where(
            competition.c.id == fx.competition_id)).scalar_one()
    home = fx.home_club_id == user
    ours, theirs = ((fx.home_goals, fx.away_goals) if home else (fx.away_goals, fx.home_goals))
    outcome = "W" if ours > theirs else "L" if ours < theirs else "D"
    if ours == theirs and fx.home_pens is not None and fx.away_pens is not None:
        pens = (fx.home_pens, fx.away_pens) if home else (fx.away_pens, fx.home_pens)
        outcome = "W" if pens[0] > pens[1] else "L"
    return SimResultOut(fixture_id=fixture_id, date=fx.date, home=names[fx.home_club_id],
                        away=names[fx.away_club_id], home_goals=fx.home_goals,
                        away_goals=fx.away_goals, outcome=outcome, competition=comp_name)


def sim_targets(conn: Connection, user: int, today: date) -> list[SimTargetOut]:
    """The "Sim to…" choices that depend on the fixture list: "Next cup match" (the user's
    next match in any competition that isn't a league), and, when he has upcoming matches in
    more than one such competition, one "Next <competition> match" each. A continental
    competition is one more competition of another type: it shows up here without changes.
    Only matches already drawn are known (a cup round is drawn once the one before is over)."""
    rows = conn.execute(
        select(fixture, competition.c.key.label("comp_key"), competition.c.name.label("comp_name"))
        .join(competition, competition.c.id == fixture.c.competition_id)
        .where(fixture.c.status == "scheduled", competition.c.type != "league",
               fixture.c.date > today.isoformat(),
               or_(fixture.c.home_club_id == user, fixture.c.away_club_id == user))
        .order_by(fixture.c.date, fixture.c.id)).all()
    if not rows:
        return []
    opponents = {r.id: r.name for r in conn.execute(select(club.c.id, club.c.name))}

    def target(key: str, label: str, comp: str, row: Row[Any]) -> SimTargetOut:
        other = row.away_club_id if row.home_club_id == user else row.home_club_id
        return SimTargetOut(key=key, label=label, competition=comp, date=row.date,
                            fixture_id=row.id, opponent=opponents[other])

    targets = [target("next_cup", "Next cup match", rows[0].comp_name, rows[0])]
    first_in: dict[str, Row[Any]] = {}
    for row in rows:
        first_in.setdefault(row.comp_key, row)
    if len(first_in) > 1:
        targets += [target(f"next:{key}", f"Next {row.comp_name} match", row.comp_name, row)
                    for key, row in first_in.items()]
    return targets


def _run(session: CareerSession, job: SimJob, user: int) -> None:
    world = get_world()
    try:
        while not job.cancel.is_set():
            with session.lock:
                if session.generation != job.generation:
                    job.stop = "abandoned"
                    return
                with session.write() as conn:
                    step = sim_step(conn, world, job.until)
                if step.fixture_id is not None:
                    job.results.append(_result(session, step.fixture_id, user))
                    session.autosave()
            job.day = step.date
            job.messages += step.messages
            if step.stop is not None:
                if step.stop == "season_end":
                    with session.read() as conn:
                        job.season_final = season_final(conn, world, user, job.messages)
                job.stop = step.stop
                break
        else:
            job.stop = "cancelled"
    except Exception as exc:  # noqa: BLE001 - shown to the user instead of dying silently
        job.stop, job.error = "error", str(exc)
    finally:
        with session.lock:
            if session.generation == job.generation and session.slot is not None:
                session.autosave()


@router.post("/career/sim")
def start(body: SimIn, request: Request) -> SimStatusOut:
    session = _session(request)
    with session.lock:
        if running(session):
            raise HTTPException(409, "a simulation is already running")
        if session.live_matches:
            raise HTTPException(409, "finish the match being watched first")
        with session.read() as conn:
            meta = read_meta(conn)
        if meta.user_club_id is None:
            raise HTTPException(409, "no club to manage")
        today = meta.current_date
        until = body.until
        if body.target is not None:
            with session.read() as conn:
                found = next((t for t in sim_targets(conn, meta.user_club_id, today)
                              if t.key == body.target), None)
            if found is None:
                raise HTTPException(400, "no such match to sim to: your next match in that "
                                         "competition isn't drawn yet")
            until = date.fromisoformat(found.date)
        if until is None:
            raise HTTPException(400, "give a date or a target to sim to")
        if not today < until <= today + timedelta(days=MAX_DAYS):
            raise HTTPException(400, f"pick a date after {today.isoformat()} and within "
                                     f"{MAX_DAYS} days")
        job = SimJob(today, until, session.generation, today)
        session.sim = job
        threading.Thread(target=_run, args=(session, job, meta.user_club_id), daemon=True,
                         name="sim-to-date").start()
        return job.status()


@router.get("/career/sim/targets")
def targets(request: Request) -> list[SimTargetOut]:
    """Where "Sim to…" can go besides a date: the user's next cup match, and so on."""
    session = _session(request)
    with session.read() as conn:
        meta = read_meta(conn)
        if meta.user_club_id is None:
            return []
        return sim_targets(conn, meta.user_club_id, meta.current_date)


@router.get("/career/sim")
def status(request: Request) -> SimStatusOut | None:
    job: SimJob | None = _session(request).sim
    return job.status() if job is not None else None


@router.post("/career/sim/stop")
def stop(request: Request) -> SimStatusOut | None:
    """Stop after the step under way (a match being played finishes first)."""
    job: SimJob | None = _session(request).sim
    if job is not None:
        job.cancel.set()
        return job.status()
    return None
