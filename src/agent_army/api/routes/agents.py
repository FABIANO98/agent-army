"""Agent management API routes."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/agents", tags=["agents"])

_orchestrator: Any = None
_database: Any = None


def configure(orchestrator: Any, database: Any) -> None:
    global _orchestrator, _database
    _orchestrator = orchestrator
    _database = database


@router.get("")
async def list_agents() -> list[dict[str, Any]]:
    """Get all agents with status and metrics."""
    if not _orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")

    agents = []
    for agent in _orchestrator._agents:
        health = await agent.health_check()
        metrics = health.get("metrics", {})
        agents.append({
            "agent_id": health.get("agent_id"),
            "name": health.get("name"),
            "agent_type": health.get("type"),
            "status": health.get("status"),
            "running": health.get("running"),
            "queue_size": health.get("queue_size", 0),
            "tasks_completed": metrics.get("tasks_completed", 0),
            "success_rate": metrics.get("success_rate", 0),
            "uptime": metrics.get("uptime_seconds", 0),
            "errors": metrics.get("recent_errors", []),
        })
    return agents


@router.get("/{agent_id}/logs")
async def get_agent_logs(
    agent_id: str,
    limit: int = 50,
    level: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Get activity logs for a specific agent."""
    if not _database:
        raise HTTPException(status_code=503, detail="Database not available")

    logs = await _database.get_agent_logs(
        agent_id=agent_id,
        level=level,
        limit=limit,
    )
    return [log.to_dict() for log in logs]
