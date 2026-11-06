"""FastAPI application factory.

Usage::

    from src.api.app import create_app

    app = create_app()          # production (file-backed DB)
    app = create_app(":memory:")  # testing
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.endpoints.compare import router as compare_router
from src.api.endpoints.households import router as households_router
from src.api.endpoints.optimization import router as optimization_router
from src.api.endpoints.portfolio import router as portfolio_router
from src.api.endpoints.reports import router as reports_router
from src.api.jobs import JobRegistry
from src.data.database import Database
from src.optimization.claiming import ClaimInputError

# Repo-root .env — backend/src/api/app.py → parents[3] = project root.
_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


def _load_env(path: Path = _ENV_PATH) -> None:
    """Load the project ``.env`` into the process environment.

    Nothing in the launch path (scripts/start.sh, scripts/dev.sh, or a manual
    ``uvicorn`` invocation) sourced ``.env``, so backend-only settings such as
    ``LLM_BASE_URL`` never reached the server — the AI-summary button stayed
    hidden even with a correctly configured ``.env``. ``override=False`` keeps
    any explicitly exported variable (e.g. ``FRONTEND_ORIGINS`` set by the
    launcher) winning over the file.
    """
    load_dotenv(path, override=False)


def create_app(db_path: str | None = None) -> FastAPI:
    """Construct and configure the FastAPI application.

    - Creates a :class:`~src.data.database.Database`, connects it inside a
      lifespan context manager, stores it on ``app.state.db``, and closes it
      on shutdown.
    - Registers CORS middleware allowing ``http://localhost:3000``.
    - Mounts the households router and exposes ``GET /health``.

    Args:
        db_path: DuckDB file path or ``":memory:"`` for an in-process DB.
            Defaults to ``<project-root>/data/retire.db`` — resolved from
            this file's location, NOT the process working directory, so the
            server always opens the same database no matter where uvicorn
            was launched from.

    Returns:
        A configured :class:`~fastapi.FastAPI` instance.
    """
    if db_path is None:
        # Production path (uvicorn --factory passes no args). Tests always
        # supply an explicit db_path and manage their own env via monkeypatch,
        # so .env loading is scoped to real server startup only.
        _load_env()
        # backend/src/api/app.py → parents[3] = project root
        default = Path(__file__).resolve().parents[3] / "data" / "retire.db"
        default.parent.mkdir(parents=True, exist_ok=True)
        db_path = str(default)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(db_path)
        db.connect()
        app.state.db = db
        app.state.jobs = JobRegistry()
        yield
        # A running job writes its run to the database: close it only once the
        # worker has stopped. One that outlasts the wait keeps the database
        # open, and the process exit ends both.
        if app.state.jobs.shutdown():
            app.state.db.close()

    app = FastAPI(title="Retirement Optimizer API", version="1.0.0", lifespan=lifespan)

    # --- middleware ----------------------------------------------------------
    # Allowed browser origins. Defaults to the dev frontend on port 3000, but
    # can be overridden when the frontend runs on a different port via the
    # FRONTEND_ORIGINS env var (comma-separated list of full origins), e.g.
    #   FRONTEND_ORIGINS="http://localhost:3005"
    origins_env = os.environ.get("FRONTEND_ORIGINS", "http://localhost:3000")
    allow_origins = [o.strip() for o in origins_env.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- routes --------------------------------------------------------------
    @app.get("/", tags=["meta"])
    def root() -> dict:
        """API root — returns service info for browser-friendly discovery."""
        return {
            "name": "Retirement Optimizer API",
            "version": "1.0.0",
            "docs": "/docs",
            "frontend": "http://localhost:3000",
        }

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        """Liveness probe.

        The ``llm`` flag indicates whether ``ANTHROPIC_API_KEY`` is configured,
        allowing the frontend to conditionally show the "Generate AI summary"
        button.
        """
        return {
            "status": "ok",
            "llm": bool(
                os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("LLM_BASE_URL")
            ),
        }

    @app.exception_handler(ClaimInputError)
    async def _claim_input_error(_: Request, exc: ClaimInputError) -> JSONResponse:
        # Contradictory or unsearchable claim-age inputs, wherever assembly or
        # the claim-age code finds them: the user must fix the inputs.
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    app.include_router(optimization_router)
    app.include_router(households_router)
    app.include_router(portfolio_router)
    app.include_router(reports_router)
    app.include_router(compare_router)

    return app
