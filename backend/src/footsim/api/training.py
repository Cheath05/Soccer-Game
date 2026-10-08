"""Position training for the user's players: which position a player is learning, how far he's
got, and his familiarity in every position (world/training.py)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from footsim.api.routes import Session, _not_simulating
from footsim.world.context import get_world
from footsim.world.meta import read_meta
from footsim.world.training import TrainingRefused, set_training, training_of

router = APIRouter(prefix="/api/players")


class FamiliarityOut(BaseModel):
    position: str
    familiarity: int  # 0-20; natural (his full rating there) from the configured threshold


class TrainingOut(BaseModel):
    position: str | None  # the position he's learning, if any
    progress: float  # toward his next point of familiarity there (0-1)
    natural: int  # the familiarity at which a player is natural in a position
    rate_per_month: float  # points a month for a player of his age
    positions: list[FamiliarityOut]


class TrainingIn(BaseModel):
    position: str | None


def _training(player_id: int, session: Session) -> TrainingOut:
    from footsim.world.training import _rate

    world = get_world()
    with session.read() as conn:
        meta = read_meta(conn)
        born = conn.execute(text("SELECT birth_date FROM person WHERE id = :p"),
                            {"p": player_id}).scalar()
        if born is None:
            raise HTTPException(404, "no such player")
        rows = conn.execute(text("SELECT position, familiarity FROM player_position WHERE "
                                 "player_id = :p ORDER BY familiarity DESC, position"),
                            {"p": player_id}).all()
        current = training_of(conn, player_id)
    from datetime import date

    age = (meta.current_date - date.fromisoformat(born)).days / 365.25
    return TrainingOut(
        position=current[0] if current else None, progress=current[1] if current else 0.0,
        natural=world.defs.development.position_training.natural,
        rate_per_month=round(_rate(world, age), 2),
        positions=[FamiliarityOut(position=r.position, familiarity=r.familiarity) for r in rows])


@router.get("/{player_id}/training")
def get_training(player_id: int, session: Session) -> TrainingOut:
    return _training(player_id, session)


@router.put("/{player_id}/training")
def put_training(player_id: int, body: TrainingIn, session: Session) -> TrainingOut:
    """Have one of the user's players learn a position (null: stop)."""
    _not_simulating(session)
    with session.write() as conn:
        meta = read_meta(conn)
        try:
            set_training(conn, get_world(), meta, player_id, body.position, meta.current_date)
        except TrainingRefused as exc:
            raise HTTPException(409, str(exc)) from exc
    session.autosave()
    return _training(player_id, session)
