"""Base Agent class with common functionality for all agents."""

from __future__ import annotations

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

from loguru import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

if TYPE_CHECKING:
    from .message_bus import Message, MessageBus
    from .registry import AgentRegistry


class AgentStatus(str, Enum):
    """Status states for an agent."""

    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"
    ERROR = "error"
    COMPLETED = "completed"
    STOPPED = "stopped"


@dataclass
class AgentMetrics:
    """Performance metrics for an agent."""

    tasks_completed: int = 0
    tasks_failed: int = 0
    total_processing_time: float = 0.0
    last_task_time: Optional[float] = None
    started_at: Optional[datetime] = None
    errors: list[str] = field(default_factory=list)

    @property
    def avg_task_time(self) -> float:
        """Calculate average task processing time."""
        if self.tasks_completed == 0:
            return 0.0
        return self.total_processing_time / self.tasks_completed

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        total = self.tasks_completed + self.tasks_failed
        if total == 0:
            return 100.0
        return (self.tasks_completed / total) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "avg_task_time": round(self.avg_task_time, 3),
            "success_rate": round(self.success_rate, 2),
            "uptime_seconds": (
                (datetime.now() - self.started_at).total_seconds()
                if self.started_at
                else 0
            ),
            "recent_errors": self.errors[-5:],
        }


class BaseAgent(ABC):
    """
    Base class for all agents in the system.

    Provides common functionality including:
    - Unique agent identification
    - Status management
    - Message queue handling
    - Logging in chat format
    - Retry logic with exponential backoff
    - Performance metrics tracking
    """

    def __init__(
        self,
        name: str,
        agent_type: str,
        message_bus: Optional[MessageBus] = None,
        registry: Optional[AgentRegistry] = None,
    ) -> None:
        """
        Initialize the base agent.

        Args:
            name: Human-readable name for the agent
            agent_type: Type/category of the agent
            message_bus: Optional message bus for inter-agent communication
            registry: Optional agent registry for discovery
        """
        self.agent_id: str = f"{agent_type}_{uuid.uuid4().hex[:8]}"
        self.name: str = name
        self.agent_type: str = agent_type
        self._status: AgentStatus = AgentStatus.IDLE
        self._message_queue: asyncio.Queue[Message] = asyncio.Queue()
        self._message_bus: Optional[MessageBus] = message_bus
        self._registry: Optional[AgentRegistry] = registry
        self._running: bool = False
        self._metrics: AgentMetrics = AgentMetrics()
        self._task: Optional[asyncio.Task[None]] = None
        self._logger = logger.bind(agent=self.name, agent_id=self.agent_id)

    @property
    def status(self) -> AgentStatus:
        """Get current agent status."""
        return self._status

    @status.setter
    def status(self, value: AgentStatus) -> None:
        """Set agent status and log the change."""
        old_status = self._status
        self._status = value
        if old_status != value:
            self.log(f"Status changed: {old_status.value} -> {value.value}", level="DEBUG")

    @property
    def metrics(self) -> AgentMetrics:
        """Get agent metrics."""
        return self._metrics

    @property
    def is_running(self) -> bool:
        """Check if agent is currently running."""
        return self._running

    def log(self, message: str, level: str = "INFO", **kwargs: Any) -> None:
        """
        Log a message in chat format.

        Args:
            message: The message to log
            level: Log level (DEBUG, INFO, WARNING, ERROR)
            **kwargs: Additional context for the log
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        chat_message = f"[{timestamp}] {self.name}: {message}"

        log_method = getattr(self._logger, level.lower(), self._logger.info)
        log_method(chat_message, **kwargs)

        # Also emit to message bus for UI updates if available
        if self._message_bus and self._running:
            asyncio.create_task(
                self._message_bus.emit_log(self.agent_id, self.name, message, level)
            )

    async def send_message(
        self,
        recipient_id: str,
        message_type: str,
        payload: dict[str, Any],
        priority: str = "normal",
    ) -> None:
        """
        Send a message to another agent.

        Args:
            recipient_id: Target agent ID or "broadcast" for all agents
            message_type: Type of message being sent
            payload: Message payload data
            priority: Message priority (low, normal, high, urgent)
        """
        if not self._message_bus:
            self.log("Cannot send message: No message bus configured", level="WARNING")
            return

        await self._message_bus.send(
            sender_id=self.agent_id,
            recipient_id=recipient_id,
            message_type=message_type,
            payload=payload,
            priority=priority,
        )
        self.log(f"Sent {message_type} to {recipient_id}", level="DEBUG")

    async def receive_message(self, message: Message) -> None:
        """
        Receive a message from the message bus.

        Args:
            message: The incoming message
        """
        await self._message_queue.put(message)
        self.log(f"Received {message.message_type} from {message.sender_id}", level="DEBUG")

    async def start(self) -> None:
        """Start the agent's main loop."""
        if self._running:
            self.log("Agent already running", level="WARNING")
            return

        self._running = True
        self._metrics.started_at = datetime.now()
        self.status = AgentStatus.IDLE
        self.log("Starting agent...")

        # Register with registry if available
        if self._registry:
            await self._registry.register(self)

        # Start the main run loop
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the agent gracefully."""
        if not self._running:
            return

        self.log("Stopping agent...")
        self._running = False
        self.status = AgentStatus.STOPPED

        # Cancel the running task
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # Unregister from registry
        if self._registry:
            await self._registry.unregister(self.agent_id)

        self.log("Agent stopped")

    async def _run_loop(self) -> None:
        """Main agent loop that processes messages and runs tasks."""
        try:
            while self._running:
                try:
                    # Check for incoming messages with timeout
                    try:
                        message = await asyncio.wait_for(
                            self._message_queue.get(), timeout=1.0
                        )
                        await self._process_message_with_retry(message)
                    except asyncio.TimeoutError:
                        pass

                    # Run the agent's main logic
                    if self._running:
                        await self.run()

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self.status = AgentStatus.ERROR
                    self._metrics.errors.append(str(e))
                    self.log(f"Error in run loop: {e}", level="ERROR")
                    await asyncio.sleep(5)  # Back off on error

        except asyncio.CancelledError:
            self.log("Agent loop cancelled", level="DEBUG")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _process_message_with_retry(self, message: Message) -> None:
        """
        Process a message with retry logic.

        Args:
            message: The message to process
        """
        start_time = time.time()
        self.status = AgentStatus.WORKING

        try:
            await self.process_message(message)
            elapsed = time.time() - start_time
            self._metrics.tasks_completed += 1
            self._metrics.total_processing_time += elapsed
            self._metrics.last_task_time = elapsed
        except Exception as e:
            self._metrics.tasks_failed += 1
            self._metrics.errors.append(f"{message.message_type}: {str(e)}")
            raise
        finally:
            self.status = AgentStatus.IDLE

    @abstractmethod
    async def run(self) -> None:
        """
        Main agent logic to be implemented by subclasses.

        This method is called continuously in the main loop.
        Implement your agent's primary behavior here.
        """
        pass

    @abstractmethod
    async def process_message(self, message: Message) -> None:
        """
        Process an incoming message.

        Args:
            message: The message to process
        """
        pass

    async def health_check(self) -> dict[str, Any]:
        """
        Perform a health check on the agent.

        Returns:
            Dictionary with health status information
        """
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "type": self.agent_type,
            "status": self.status.value,
            "running": self._running,
            "queue_size": self._message_queue.qsize(),
            "metrics": self._metrics.to_dict(),
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.agent_id}, name={self.name}, status={self.status.value})>"
