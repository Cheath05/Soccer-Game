"""FastAPI application: the /api routes plus, when built, the frontend itself.

Presentation layer only: no simulation logic lives here.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from footsim import __version__
from footsim.api.live import router as live_router
from footsim.api.routes import router
from footsim.api.session import CareerSession, NoCareer, default_session
from footsim.api.sim import router as sim_router
from footsim.api.transfers import router as transfers_router
from footsim.core.build_info import build_info
from footsim.core.paths import REPO_ROOT
from footsim.persistence.database import SchemaMismatch

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def create_app(session: CareerSession | None = None, frontend: Path | None = FRONTEND_DIST
               ) -> FastAPI:
    build_info()  # read git now, so the build reported is the code this process loaded
    app = FastAPI(title="footsim", version=__version__)
    app.state.session = session or default_session()

    @app.exception_handler(NoCareer)
    def _no_career(_request: Request, exc: NoCareer) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(SchemaMismatch)
    def _schema(_request: Request, exc: SchemaMismatch) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    app.include_router(router)
    app.include_router(live_router)
    app.include_router(sim_router)
    app.include_router(transfers_router)

    if frontend is not None and (frontend / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            candidate = (frontend / path).resolve()
            if path and candidate.is_file() and frontend.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(frontend / "index.html")

    return app


app = create_app()
