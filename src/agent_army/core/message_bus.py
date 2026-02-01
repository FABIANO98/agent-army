"""Central Message Bus system for inter-agent communication."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from heapq import heappop, heappush
from typing import TYPE_CHECKING, Any, Callable, Optional

from loguru import logger

if TYPE_CHECKING:
    from .base_agent import BaseAgent


class MessageType(str, Enum):
    """Types of messages that can be sent between agents."""

    # Prospect related
    NEW_PROSPECTS = "new_prospects"
    PROSPECT_RESEARCH_COMPLETE = "prospect_research_complete"

    # Email related
    EMAIL_DRAFT_REQUEST = "email_draft_request"
    EMAIL_DRAFT_READY = "email_draft_ready"
    EMAIL_QUALITY_CHECK = "email_quality_check"
    EMAIL_APPROVED = "email_approved"
    EMAIL_REJECTED = "email_rejected"
    EMAIL_SENT = "email_sent"

    # Response related
    RESPONSE_RECEIVED = "response_received"
    RESPONSE_CATEGORIZED = "response_categorized"
    RESPONSE_DRAFT_READY = "response_draft_ready"

    # Deal related
    DEAL_STAGE_UPDATE = "deal_stage_update"
    DEAL_ALERT = "deal_alert"

    # System
    HEALTH_CHECK = "health_check"
    HEALTH_RESPONSE = "health_response"
    BROADCAST = "broadcast"
    AGENT_LOG = "agent_log"
    SHUTDOWN = "shutdown"


class Priority(str, Enum):
    """Message priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

    @property
    def value_int(self) -> int:
        """Get integer value for priority comparison."""
        return {"urgent": 0, "high": 1, "normal": 2, "low": 3}[self.value]


@dataclass(order=True)
class PrioritizedMessage:
    """Wrapper for priority queue ordering."""

    priority: int
    timestamp: float
    message: Any = field(compare=False)


@dataclass
class Message:
    """
    A message sent between agents.

    Attributes:
        id: Unique message identifier
        sender_id: ID of the sending agent
        recipient_id: ID of the recipient agent (or "broadcast")
        message_type: Type of the message
        payload: Message data
        timestamp: When the message was created
        priority: Message priority level
        mentions: List of mentioned agent IDs (@mentions)
    """

    id: str
    sender_id: str
    recipient_id: str
    message_type: str
    payload: dict[str, Any]
    timestamp: datetime
    priority: Priority = Priority.NORMAL
    mentions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert message to dictionary."""
        return {
            "id": self.id,
            "from": self.sender_id,
            "to": self.recipient_id,
            "type": self.message_type,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "priority": self.priority.value,
            "mentions": self.mentions,
        }

    def to_json(self) -> str:
        """Convert message to JSON string."""
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        """Create message from dictionary."""
        return cls(
            id=data["id"],
            sender_id=data["from"],
            recipient_id=data["to"],
            message_type=data["type"],
            payload=data["payload"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            priority=Priority(data.get("priority", "normal")),
            mentions=data.get("mentions", []),
        )


class MessageBus:
    """
    Central message bus for agent communication.

    Features:
    - Agent registration and discovery
    - Priority queue for message ordering
    - Support for @mentions
    - Broadcast messages
    - Message history for replay
    - WebSocket integration for real-time updates
    """

    MENTION_PATTERN = re.compile(r"@(\w+)")

    def __init__(self, history_size: int = 1000) -> None:
        """
        Initialize the message bus.

        Args:
            history_size: Maximum number of messages to keep in history
        """
        self._agents: dict[str, BaseAgent] = {}
        self._agent_names: dict[str, str] = {}  # name -> agent_id mapping
        self._priority_queue: list[PrioritizedMessage] = []
        self._history: deque[Message] = deque(maxlen=history_size)
        self._subscribers: dict[str, list[Callable[[Message], Any]]] = {}
        self._websocket_handlers: list[Callable[[dict[str, Any]], Any]] = []
        self._running: bool = False
        self._process_task: Optional[asyncio.Task[None]] = None
        self._lock = asyncio.Lock()
        self._logger = logger.bind(component="MessageBus")

    async def start(self) -> None:
        """Start the message bus processing loop."""
        if self._running:
            return

        self._running = True
        self._process_task = asyncio.create_task(self._process_loop())
        self._logger.info("Message bus started")

    async def stop(self) -> None:
        """Stop the message bus."""
        self._running = False
        if self._process_task:
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass
        self._logger.info("Message bus stopped")

    def register_agent(self, agent: BaseAgent) -> None:
        """
        Register an agent with the message bus.

        Args:
            agent: The agent to register
        """
        self._agents[agent.agent_id] = agent
        self._agent_names[agent.name.lower()] = agent.agent_id
        self._agent_names[agent.agent_type.lower()] = agent.agent_id
        self._logger.info(f"Agent registered: {agent.name} ({agent.agent_id})")

    def unregister_agent(self, agent_id: str) -> None:
        """
        Unregister an agent from the message bus.

        Args:
            agent_id: ID of the agent to unregister
        """
        if agent_id in self._agents:
            agent = self._agents[agent_id]
            del self._agents[agent_id]
            # Clean up name mappings
            self._agent_names = {
                k: v for k, v in self._agent_names.items() if v != agent_id
            }
            self._logger.info(f"Agent unregistered: {agent.name}")

    def get_agent(self, identifier: str) -> Optional[BaseAgent]:
        """
        Get an agent by ID or name.

        Args:
            identifier: Agent ID or name

        Returns:
            The agent if found, None otherwise
        """
        if identifier in self._agents:
            return self._agents[identifier]

        agent_id = self._agent_names.get(identifier.lower())
        if agent_id:
            return self._agents.get(agent_id)

        return None

    async def send(
        self,
        sender_id: str,
        recipient_id: str,
        message_type: str,
        payload: dict[str, Any],
        priority: str = "normal",
    ) -> str:
        """
        Send a message to an agent or broadcast to all.

        Args:
            sender_id: ID of the sending agent
            recipient_id: ID of the recipient or "broadcast"
            message_type: Type of message
            payload: Message payload
            priority: Message priority

        Returns:
            The message ID
        """
        # Parse @mentions from payload text if present
        mentions = []
        if "text" in payload:
            mentions = self._parse_mentions(payload["text"])

        message = Message(
            id=f"msg_{uuid.uuid4().hex[:12]}",
            sender_id=sender_id,
            recipient_id=recipient_id,
            message_type=message_type,
            payload=payload,
            timestamp=datetime.now(),
            priority=Priority(priority),
            mentions=mentions,
        )

        async with self._lock:
            # Add to priority queue
            heappush(
                self._priority_queue,
                PrioritizedMessage(
                    priority=Priority(priority).value_int,
                    timestamp=message.timestamp.timestamp(),
                    message=message,
                ),
            )

            # Add to history
            self._history.append(message)

        self._logger.debug(f"Message queued: {message.id} ({message_type})")
        return message.id

    def _parse_mentions(self, text: str) -> list[str]:
        """
        Parse @mentions from text.

        Args:
            text: Text to parse

        Returns:
            List of mentioned agent IDs
        """
        mentions = []
        for match in self.MENTION_PATTERN.finditer(text):
            name = match.group(1).lower()
            agent_id = self._agent_names.get(name)
            if agent_id:
                mentions.append(agent_id)
        return mentions

    async def _process_loop(self) -> None:
        """Process messages from the priority queue."""
        try:
            while self._running:
                if not self._priority_queue:
                    await asyncio.sleep(0.1)
                    continue

                async with self._lock:
                    if self._priority_queue:
                        prioritized = heappop(self._priority_queue)
                        message = prioritized.message
                    else:
                        continue

                await self._deliver_message(message)

        except asyncio.CancelledError:
            pass

    async def _deliver_message(self, message: Message) -> None:
        """
        Deliver a message to its recipient(s).

        Args:
            message: The message to deliver
        """
        recipients: list[BaseAgent] = []

        if message.recipient_id == "broadcast":
            recipients = list(self._agents.values())
        else:
            agent = self.get_agent(message.recipient_id)
            if agent:
                recipients = [agent]

        # Also deliver to mentioned agents
        for agent_id in message.mentions:
            agent = self._agents.get(agent_id)
            if agent and agent not in recipients:
                recipients.append(agent)

        for agent in recipients:
            if agent.agent_id != message.sender_id:  # Don't send to self
                try:
                    await agent.receive_message(message)
                except Exception as e:
                    self._logger.error(f"Failed to deliver message to {agent.name}: {e}")

        # Notify subscribers
        await self._notify_subscribers(message)

        # Send to WebSocket handlers for UI updates
        await self._notify_websockets(message.to_dict())

    async def _notify_subscribers(self, message: Message) -> None:
        """Notify all subscribers of a message type."""
        handlers = self._subscribers.get(message.message_type, [])
        handlers.extend(self._subscribers.get("*", []))  # Wildcard subscribers

        for handler in handlers:
            try:
                result = handler(message)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                self._logger.error(f"Subscriber error: {e}")

    async def _notify_websockets(self, data: dict[str, Any]) -> None:
        """Send data to all WebSocket handlers."""
        for handler in self._websocket_handlers:
            try:
                result = handler(data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                self._logger.error(f"WebSocket handler error: {e}")

    def subscribe(self, message_type: str, handler: Callable[[Message], Any]) -> None:
        """
        Subscribe to a message type.

        Args:
            message_type: Type to subscribe to (or "*" for all)
            handler: Callback function for messages
        """
        if message_type not in self._subscribers:
            self._subscribers[message_type] = []
        self._subscribers[message_type].append(handler)

    def unsubscribe(self, message_type: str, handler: Callable[[Message], Any]) -> None:
        """Unsubscribe from a message type."""
        if message_type in self._subscribers:
            self._subscribers[message_type] = [
                h for h in self._subscribers[message_type] if h != handler
            ]

    def add_websocket_handler(self, handler: Callable[[dict[str, Any]], Any]) -> None:
        """Add a WebSocket handler for real-time updates."""
        self._websocket_handlers.append(handler)

    def remove_websocket_handler(self, handler: Callable[[dict[str, Any]], Any]) -> None:
        """Remove a WebSocket handler."""
        self._websocket_handlers = [h for h in self._websocket_handlers if h != handler]

    async def emit_log(
        self, agent_id: str, agent_name: str, message: str, level: str
    ) -> None:
        """
        Emit a log message for UI updates.

        Args:
            agent_id: ID of the agent
            agent_name: Name of the agent
            message: Log message
            level: Log level
        """
        log_data = {
            "type": "agent_log",
            "agent_id": agent_id,
            "agent_name": agent_name,
            "message": message,
            "level": level,
            "timestamp": datetime.now().isoformat(),
        }
        await self._notify_websockets(log_data)

    def get_history(
        self,
        limit: int = 100,
        message_type: Optional[str] = None,
        sender_id: Optional[str] = None,
    ) -> list[Message]:
        """
        Get message history.

        Args:
            limit: Maximum number of messages to return
            message_type: Filter by message type
            sender_id: Filter by sender

        Returns:
            List of messages matching the criteria
        """
        messages = list(self._history)

        if message_type:
            messages = [m for m in messages if m.message_type == message_type]
        if sender_id:
            messages = [m for m in messages if m.sender_id == sender_id]

        return messages[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Get message bus statistics."""
        return {
            "registered_agents": len(self._agents),
            "queue_size": len(self._priority_queue),
            "history_size": len(self._history),
            "subscribers": {k: len(v) for k, v in self._subscribers.items()},
            "websocket_handlers": len(self._websocket_handlers),
        }
