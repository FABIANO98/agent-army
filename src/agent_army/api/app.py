"""FastAPI application setup."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routes import agents, dashboard, tasks, websocket


def create_app(
    orchestrator: Any = None,
    database: Any = None,
    task_manager: Any = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Agent Army",
        description="AI-Team Web Dashboard for B2B Lead Generation",
        version="0.2.0",
    )

    # CORS for React dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Configure routes with dependencies
    tasks.configure(database=database, task_manager=task_manager)
    agents.configure(orchestrator=orchestrator, database=database)
    dashboard.configure(database=database, orchestrator=orchestrator)

    # Register routers
    app.include_router(tasks.router)
    app.include_router(agents.router)
    app.include_router(dashboard.router)
    app.include_router(websocket.router)

    # Serve React build if it exists
    dashboard_path = Path(__file__).parent.parent.parent.parent / "dashboard" / "dist"
    if dashboard_path.exists():
        index_html = dashboard_path / "index.html"

        # SPA catch-all: serve index.html for non-API routes (client-side routing)
        @app.get("/{path:path}")
        async def spa_fallback(request: Request, path: str) -> FileResponse:
            # Serve static assets directly if they exist
            file_path = dashboard_path / path
            if file_path.is_file():
                return FileResponse(file_path)
            # Otherwise serve index.html for client-side routing
            return FileResponse(index_html)

    # Register WebSocket handler with message bus
    if orchestrator and orchestrator._message_bus:
        orchestrator._message_bus.add_websocket_handler(websocket.manager.broadcast)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
