"""Database components for the Agent Army system."""

from .models import (
    Base,
    Prospect,
    CompanyProfile,
    Email,
    Response,
    Deal,
    AgentLog,
    DealStage,
    Task,
    TaskStatus,
    Subtask,
    TaskResult,
    AgentCommunication,
)
from .database import Database

__all__ = [
    "Base",
    "Prospect",
    "CompanyProfile",
    "Email",
    "Response",
    "Deal",
    "AgentLog",
    "DealStage",
    "Task",
    "TaskStatus",
    "Subtask",
    "TaskResult",
    "AgentCommunication",
    "Database",
]
