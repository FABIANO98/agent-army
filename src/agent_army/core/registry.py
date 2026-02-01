"""Agent Registry for managing and discovering agents."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from loguru import logger

if TYPE_CHECKING:
    from .base_agent import BaseAgent


class AgentRegistry:
    """
    Central registry for all agents in the system.

    Features:
    - Agent registration and discovery
    - Health checks for all agents
    - Graceful shutdown coordination
    - Automatic agent restart on crash
    """

    def __init__(self, health_check_interval: float = 30.0) -> None:
        """
        Initialize the agent registry.

        Args:
            health_check_interval: Seconds between health checks
        """
        self._agents: dict[str, BaseAgent] = {}
        self._agent_types: dict[str, list[str]] = {}  # type -> [agent_ids]
        self._agent_names: dict[str, str] = {}  # name -> agent_id
        self._health_check_interval = health_check_interval
        self._health_task: Optional[asyncio.Task[None]] = None
        self._running: bool = False
        self._restart_enabled: bool = True
        self._lock = asyncio.Lock()
        self._logger = logger.bind(component="AgentRegistry")

    async def start(self) -> None:
        """Start the registry and health check loop."""
        if self._running:
            return

        self._running = True
        self._health_task = asyncio.create_task(self._health_check_loop())
        self._logger.info("Agent registry started")

    async def stop(self) -> None:
        """Stop the registry."""
        self._running = False
        self._restart_enabled = False

        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass

        self._logger.info("Agent registry stopped")

    async def register(self, agent: BaseAgent) -> None:
        """
        Register an agent with the registry.

        Args:
            agent: The agent to register
        """
        async with self._lock:
            self._agents[agent.agent_id] = agent
            self._agent_names[agent.name.lower()] = agent.agent_id

            # Track by type
            if agent.agent_type not in self._agent_types:
                self._agent_types[agent.agent_type] = []
            if agent.agent_id not in self._agent_types[agent.agent_type]:
                self._agent_types[agent.agent_type].append(agent.agent_id)

        self._logger.info(f"Registered agent: {agent.name} ({agent.agent_id})")

    async def unregister(self, agent_id: str) -> None:
        """
        Unregister an agent from the registry.

        Args:
            agent_id: ID of the agent to unregister
        """
        async with self._lock:
            if agent_id not in self._agents:
                return

            agent = self._agents[agent_id]
            del self._agents[agent_id]

            # Clean up name mapping
            self._agent_names = {
                k: v for k, v in self._agent_names.items() if v != agent_id
            }

            # Clean up type mapping
            if agent.agent_type in self._agent_types:
                self._agent_types[agent.agent_type] = [
                    aid for aid in self._agent_types[agent.agent_type] if aid != agent_id
                ]

        self._logger.info(f"Unregistered agent: {agent.name}")

    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """
        Get an agent by ID.

        Args:
            agent_id: The agent ID

        Returns:
            The agent if found, None otherwise
        """
        return self._agents.get(agent_id)

    def get_agent_by_name(self, name: str) -> Optional[BaseAgent]:
        """
        Get an agent by name.

        Args:
            name: The agent name (case-insensitive)

        Returns:
            The agent if found, None otherwise
        """
        agent_id = self._agent_names.get(name.lower())
        if agent_id:
            return self._agents.get(agent_id)
        return None

    def get_agents_by_type(self, agent_type: str) -> list[BaseAgent]:
        """
        Get all agents of a specific type.

        Args:
            agent_type: The agent type

        Returns:
            List of agents of that type
        """
        agent_ids = self._agent_types.get(agent_type, [])
        return [self._agents[aid] for aid in agent_ids if aid in self._agents]

    def get_all_agents(self) -> list[BaseAgent]:
        """Get all registered agents."""
        return list(self._agents.values())

    async def _health_check_loop(self) -> None:
        """Periodically check health of all agents."""
        try:
            while self._running:
                await asyncio.sleep(self._health_check_interval)
                await self._check_all_agents()
        except asyncio.CancelledError:
            pass

    async def _check_all_agents(self) -> None:
        """Check health of all agents and restart crashed ones."""
        agents_to_restart: list[BaseAgent] = []

        async with self._lock:
            for agent_id, agent in list(self._agents.items()):
                try:
                    health = await agent.health_check()

                    if not health.get("running", False):
                        self._logger.warning(f"Agent {agent.name} not running")
                        if self._restart_enabled:
                            agents_to_restart.append(agent)

                except Exception as e:
                    self._logger.error(f"Health check failed for {agent.name}: {e}")
                    if self._restart_enabled:
                        agents_to_restart.append(agent)

        # Restart crashed agents
        for agent in agents_to_restart:
            await self._restart_agent(agent)

    async def _restart_agent(self, agent: BaseAgent) -> None:
        """
        Attempt to restart a crashed agent.

        Args:
            agent: The agent to restart
        """
        self._logger.info(f"Attempting to restart agent: {agent.name}")

        try:
            await agent.stop()
            await asyncio.sleep(1)  # Brief pause before restart
            await agent.start()
            self._logger.info(f"Successfully restarted agent: {agent.name}")
        except Exception as e:
            self._logger.error(f"Failed to restart agent {agent.name}: {e}")

    async def shutdown_all(self) -> None:
        """Gracefully shutdown all registered agents."""
        self._logger.info("Initiating graceful shutdown of all agents...")
        self._restart_enabled = False

        # Create shutdown tasks for all agents
        shutdown_tasks = []
        for agent in list(self._agents.values()):
            self._logger.info(f"Stopping agent: {agent.name}")
            shutdown_tasks.append(agent.stop())

        # Wait for all agents to stop
        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)

        self._logger.info("All agents stopped")

    async def get_system_health(self) -> dict[str, Any]:
        """
        Get health status of the entire system.

        Returns:
            Dictionary with system health information
        """
        agent_health: list[dict[str, Any]] = []

        for agent in self._agents.values():
            try:
                health = await agent.health_check()
                agent_health.append(health)
            except Exception as e:
                agent_health.append({
                    "agent_id": agent.agent_id,
                    "name": agent.name,
                    "error": str(e),
                })

        healthy_count = sum(1 for h in agent_health if h.get("running", False))
        total_count = len(agent_health)

        return {
            "timestamp": datetime.now().isoformat(),
            "total_agents": total_count,
            "healthy_agents": healthy_count,
            "unhealthy_agents": total_count - healthy_count,
            "system_status": "healthy" if healthy_count == total_count else "degraded",
            "agents": agent_health,
        }

    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics."""
        return {
            "total_agents": len(self._agents),
            "agents_by_type": {k: len(v) for k, v in self._agent_types.items()},
            "running": self._running,
            "restart_enabled": self._restart_enabled,
        }
