"""Task management API routes."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from ..schemas import TaskCreateRequest, TaskResponse, SubtaskResponse, TaskResultResponse

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

# These will be set by the app on startup
_database: Any = None
_task_manager: Any = None


def configure(database: Any, task_manager: Any) -> None:
    global _database, _task_manager
    _database = database
    _task_manager = task_manager


@router.post("", response_model=dict)
async def create_task(request: TaskCreateRequest) -> dict[str, Any]:
    """Create a new task from natural language description."""
    if not _task_manager:
        raise HTTPException(status_code=503, detail="Task manager not available")

    task_id = await _task_manager.create_task(
        title=request.title,
        description=request.description,
    )
    return {"id": task_id, "status": "created"}


@router.get("")
async def list_tasks(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List all tasks with optional status filter."""
    if not _database:
        raise HTTPException(status_code=503, detail="Database not available")

    tasks = await _database.list_tasks(status=status, limit=limit, offset=offset)
    return [t.to_dict() for t in tasks]


@router.get("/{task_id}")
async def get_task(task_id: int) -> dict[str, Any]:
    """Get task details including subtasks and results."""
    if not _database:
        raise HTTPException(status_code=503, detail="Database not available")

    task = await _database.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    result = task.to_dict()

    subtasks = await _database.get_subtasks(task_id)
    result["subtasks"] = [st.to_dict() for st in subtasks]

    results = await _database.get_task_results(task_id)
    result["results"] = [r.to_dict() for r in results]

    return result


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: int) -> dict[str, str]:
    """Cancel a running task."""
    if not _database:
        raise HTTPException(status_code=503, detail="Database not available")

    task = await _database.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status in ("completed", "failed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Task already {task.status}")

    await _database.update_task(task_id, status="cancelled")
    return {"status": "cancelled"}
