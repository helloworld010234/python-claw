"""FastAPI application factory for the skeleton milestone."""

from __future__ import annotations

from fastapi import FastAPI

from python_claw.__about__ import __version__


def create_app() -> FastAPI:
    """Create the FastAPI app without wiring business services yet."""
    app = FastAPI(
        title="python-claw",
        version=__version__,
        summary="Python AgentOps Harness skeleton.",
    )

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {
            "service": "python-claw",
            "status": "ok",
            "stage": "skeleton",
        }

    return app


app = create_app()
