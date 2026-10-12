"""How the server hosts its players (data/config/server.yaml): accounts, sign-in, sessions
and the worker processes heavy simulation runs in. None of it changes the game."""

from pydantic import Field

from footsim.defs.common import DefModel


class ServerDef(DefModel):
    session_days: int = Field(gt=0)  # a sign-in lasts this long without being used
    min_password_length: int = Field(ge=4)
    login_attempts: int = Field(gt=0)  # failed sign-ins allowed per name and per address...
    login_window_seconds: float = Field(gt=0)  # ...within this window
    failure_delay_seconds: float = Field(ge=0)  # each failed sign-in waits this long
    idle_close_minutes: float = Field(gt=0)  # a player's open career is closed after this
    sim_workers: int = Field(ge=0)  # processes for heavy simulation; 0 runs it in the server
    owner_keep_backups: int = Field(ge=1)  # manual-save backups kept per slot
    friend_keep_backups: int = Field(ge=1)
