"""FastAPI entry point. Presentation layer only: no simulation logic lives here."""

from fastapi import FastAPI

from footsim import __version__

app = FastAPI(title="footsim", version=__version__)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
