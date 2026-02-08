"""Dashboard API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_database: Any = None
_orchestrator: Any = None


def configure(database: Any, orchestrator: Any) -> None:
    global _database, _orchestrator
    _database = database
    _orchestrator = orchestrator


@router.get("/stats")
async def get_stats() -> dict[str, Any]:
    """Get aggregated dashboard statistics."""
    if not _database:
        raise HTTPException(status_code=503, detail="Database not available")

    stats = await _database.get_dashboard_stats()

    # Add agent counts
    active_agents = 0
    total_agents = 0
    if _orchestrator:
        active_agents = sum(1 for a in _orchestrator._agents if a.is_running)
        total_agents = len(_orchestrator._agents)

    stats["active_agents"] = active_agents
    stats["total_agents"] = total_agents
    # Map field names to frontend expectations
    stats["running_tasks"] = stats.pop("active_tasks", 0)
    # Use the actual today count; remove total_prospects from response
    stats.pop("total_prospects", None)
    stats["llm_available"] = (
        _orchestrator._llm_service is not None if _orchestrator else False
    )
    return stats


@router.get("/communications")
async def get_communications(
    limit: int = 100,
    task_id: int | None = None,
) -> list[dict[str, Any]]:
    """Get agent communication log."""
    if not _database:
        raise HTTPException(status_code=503, detail="Database not available")

    comms = await _database.get_communications(limit=limit, task_id=task_id)
    return [c.to_dict() for c in comms]


@router.get("/report")
async def get_daily_report() -> dict[str, Any]:
    """Get today's daily report."""
    if not _database:
        raise HTTPException(status_code=503, detail="Database not available")

    return await _database.get_daily_report()
