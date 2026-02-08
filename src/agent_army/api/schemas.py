"""Pydantic schemas for API request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    priority: int = Field(default=5, ge=1, le=10)


class TaskResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    status: str
    priority: int
    plan: Optional[dict[str, Any]] = None
    result_summary: Optional[str] = None
    progress_pct: int = 0
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    subtasks: list[SubtaskResponse] = []
    results: list[TaskResultResponse] = []

    class Config:
        from_attributes = True


class SubtaskResponse(BaseModel):
    id: int
    task_id: int
    title: str
    description: Optional[str] = None
    assigned_agent: Optional[str] = None
    status: str
    sequence_order: int = 0
    depends_on: Optional[list[int]] = None
    input_data: Optional[dict[str, Any]] = None
    output_data: Optional[dict[str, Any]] = None


class TaskResultResponse(BaseModel):
    id: int
    task_id: int
    result_type: str
    title: Optional[str] = None
    data: Optional[dict[str, Any]] = None
    created_at: Optional[str] = None


class AgentResponse(BaseModel):
    agent_id: str
    name: str
    type: str
    status: str
    running: bool
    queue_size: int
    metrics: dict[str, Any] = {}


class DashboardStats(BaseModel):
    active_agents: int = 0
    active_tasks: int = 0
    pipeline_value: float = 0
    emails_today: int = 0
    total_prospects: int = 0
    total_tasks: int = 0


class CommunicationResponse(BaseModel):
    id: int
    sender_agent: str
    receiver_agent: str
    message_type: str
    summary: Optional[str] = None
    task_id: Optional[int] = None
    timestamp: Optional[str] = None


# Fix forward reference
TaskResponse.model_rebuild()
