"""Logging setup for the Agent Army system."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from loguru import logger

from .config import LoggingSettings


def setup_logging(settings: LoggingSettings | None = None) -> None:
    """
    Configure logging for the application.

    Args:
        settings: Logging settings to use
    """
    if settings is None:
        settings = LoggingSettings()

    # Remove default handler
    logger.remove()

    # Add console handler with rich formatting
    logger.add(
        sys.stderr,
        format=settings.format,
        level=settings.level,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # Add file handler if configured
    if settings.file_path:
        log_path = Path(settings.file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            settings.file_path,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[component]} | {message}",
            level=settings.level,
            rotation=settings.rotation,
            retention=settings.retention,
            compression="gz",
        )

    # Set default context
    logger.configure(extra={"component": "system"})


def get_logger(component: str) -> Any:
    """
    Get a logger with component context.

    Args:
        component: Name of the component

    Returns:
        Bound logger instance
    """
    return logger.bind(component=component)


class AgentLogHandler:
    """Handler for capturing agent logs and forwarding to message bus."""

    def __init__(self, agent_id: str, agent_name: str) -> None:
        """
        Initialize the log handler.

        Args:
            agent_id: ID of the agent
            agent_name: Name of the agent
        """
        self.agent_id = agent_id
        self.agent_name = agent_name
        self._logs: list[dict[str, Any]] = []

    def write(self, message: str) -> None:
        """Write a log message."""
        self._logs.append({
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "message": message.strip(),
        })

    def get_logs(self) -> list[dict[str, Any]]:
        """Get all captured logs."""
        return self._logs.copy()

    def clear(self) -> None:
        """Clear captured logs."""
        self._logs.clear()
