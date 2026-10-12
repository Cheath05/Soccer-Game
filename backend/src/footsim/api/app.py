"""FastAPI application: the /api routes plus, when built, the frontend itself.

Presentation layer only: no simulation logic lives here.
"""

from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from footsim import __version__
from footsim.api import auth
from footsim.api.live import router as live_router
from footsim.api.market_overview import router as market_overview_router
from footsim.api.routes import router
from footsim.api.session import CareerSession, NoCareer, SessionRegistry, default_registry
from footsim.api.sim import router as sim_router
from footsim.api.training import router as training_router
from footsim.api.transfers import router as transfers_router
from footsim.core.build_info import build_info
from footsim.core.paths import REPO_ROOT
from footsim.persistence.database import SchemaMismatch

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def create_app(session: CareerSession | None = None, frontend: Path | None = FRONTEND_DIST,
               registry: SessionRegistry | None = None) -> FastAPI:
    """The app. ``session`` (tests): one career for everyone, without accounts. ``registry``:
    the careers as given. Neither: as configured (``default_registry``, FOOTSIM_AUTH)."""
    build_info()  # read git now, so the build reported is the code this process loaded
    app = FastAPI(title="footsim", version=__version__)
    if registry is None:
        registry = SessionRegistry.single(session) if session else default_registry()
    app.state.registry = registry
    app.state.login_throttle = auth.Throttle()

    @app.middleware("http")
    async def _signed_in(request: Request,
                         call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Every /api request but health and signing in is someone's: who, is kept for the
        routes (``auth.session_for``); nobody signed in gets 401."""
        path = request.url.path
        if path.startswith("/api/") and not auth.is_open(path):
            account = await auth.signed_in(request)
            if account is None:
                return JSONResponse(status_code=401, content={"detail": "sign in first"})
            request.state.account = account
        return await call_next(request)

    @app.exception_handler(NoCareer)
    def _no_career(_request: Request, exc: NoCareer) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(SchemaMismatch)
    def _schema(_request: Request, exc: SchemaMismatch) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    app.include_router(auth.router)
    app.include_router(router)
    app.include_router(live_router)
    app.include_router(sim_router)
    app.include_router(transfers_router)
    app.include_router(training_router)
    app.include_router(market_overview_router)

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
