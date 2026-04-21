"""FastAPI application factory.

Mounts the SPA static directory at `/` and exposes API routes under `/api/...`.
Route registration order matters — API routes are declared before the static
mount so that `/api/*` requests never fall through to the static handler.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from family_chores import __version__
from family_chores.config import Options, load_options

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(options: Options | None = None) -> FastAPI:
    opts = options if options is not None else load_options()
    app = FastAPI(
        title="Family Chores",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/info")
    async def info() -> dict[str, object]:
        return {
            "version": __version__,
            "log_level": opts.log_level,
            "week_starts_on": opts.week_starts_on,
            "sound_default": opts.sound_default,
        }

    if STATIC_DIR.is_dir() and any(STATIC_DIR.iterdir()):
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    else:
        @app.get("/", response_class=HTMLResponse)
        async def fallback() -> str:
            return (
                "<!DOCTYPE html><html><body style='font-family:system-ui;padding:2rem'>"
                "<h1>Family Chores</h1>"
                "<p>Backend is running. Static assets not yet built — see milestone 6.</p>"
                "<p>Try <code>GET /api/health</code>.</p>"
                "</body></html>"
            )

    return app
