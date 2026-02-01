"""Main Orchestrator for the Agent Army system."""

from __future__ import annotations

import asyncio
import signal
from datetime import datetime
from typing import Any, Optional

from loguru import logger
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from .agents import (
    DealTrackerAgent,
    EmailSenderAgent,
    EmailWriterAgent,
    ProspectFinderAgent,
    QualityControlAgent,
    ResearchManagerAgent,
    ResponseMonitorAgent,
    ResponseWriterAgent,
)
from .core import AgentRegistry, MessageBus
from .db import Database
from .utils import Settings, load_config, setup_logging


class Orchestrator:
    """
    Main orchestrator for the Agent Army system.

    Responsibilities:
    - Start and stop all agents
    - Coordinate message flow
    - Monitor system health
    - Handle graceful shutdown
    - Display live agent activity
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        """
        Initialize the orchestrator.

        Args:
            config_path: Optional path to configuration file
        """
        self._settings = load_config(config_path)
        self._console = Console()
        self._message_bus = MessageBus()
        self._registry = AgentRegistry()
        self._database: Optional[Database] = None
        self._agents: list[Any] = []
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._logger = logger.bind(component="Orchestrator")

    async def initialize(self) -> None:
        """Initialize all components."""
        # Setup logging
        setup_logging(self._settings.logging)
        self._logger.info("Initializing Agent Army...")

        # Initialize database
        self._database = Database(
            self._settings.database.database_url,
            echo=self._settings.database.echo_sql,
        )
        await self._database.init_db()
        self._logger.info("Database initialized")

        # Start message bus
        await self._message_bus.start()
        self._logger.info("Message bus started")

        # Start registry
        await self._registry.start()
        self._logger.info("Agent registry started")

        # Create all agents
        self._agents = [
            ProspectFinderAgent(
                message_bus=self._message_bus,
                registry=self._registry,
                database=self._database,
                settings=self._settings,
            ),
            ResearchManagerAgent(
                message_bus=self._message_bus,
                registry=self._registry,
                database=self._database,
                settings=self._settings,
            ),
            EmailWriterAgent(
                message_bus=self._message_bus,
                registry=self._registry,
                database=self._database,
                settings=self._settings,
            ),
            QualityControlAgent(
                message_bus=self._message_bus,
                registry=self._registry,
                database=self._database,
                settings=self._settings,
            ),
            EmailSenderAgent(
                message_bus=self._message_bus,
                registry=self._registry,
                database=self._database,
                settings=self._settings,
            ),
            ResponseMonitorAgent(
                message_bus=self._message_bus,
                registry=self._registry,
                database=self._database,
                settings=self._settings,
            ),
            ResponseWriterAgent(
                message_bus=self._message_bus,
                registry=self._registry,
                database=self._database,
                settings=self._settings,
            ),
            DealTrackerAgent(
                message_bus=self._message_bus,
                registry=self._registry,
                database=self._database,
                settings=self._settings,
            ),
        ]

        # Register agents with message bus
        for agent in self._agents:
            self._message_bus.register_agent(agent)

        self._logger.info(f"Created {len(self._agents)} agents")

    async def start(self) -> None:
        """Start all agents and begin orchestration."""
        self._running = True

        # Setup signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._signal_handler)

        self._logger.info("Starting all agents...")
        self._console.print("[bold green]Starting Agent Army...[/bold green]")

        # Start all agents
        start_tasks = [agent.start() for agent in self._agents]
        await asyncio.gather(*start_tasks)

        self._console.print(f"[bold green]{len(self._agents)} agents started![/bold green]")

        # Run main loop with live display
        try:
            await self._run_with_display()
        except asyncio.CancelledError:
            pass

        await self.shutdown()

    async def _run_with_display(self) -> None:
        """Run main loop with live status display."""
        with Live(self._generate_status_table(), refresh_per_second=1, console=self._console) as live:
            while self._running and not self._shutdown_event.is_set():
                live.update(self._generate_status_table())
                await asyncio.sleep(1)

    def _generate_status_table(self) -> Panel:
        """Generate status table for display."""
        table = Table(title="Agent Army Status", show_header=True, header_style="bold cyan")
        table.add_column("Agent", style="dim", width=20)
        table.add_column("Status", width=12)
        table.add_column("Tasks", justify="right", width=8)
        table.add_column("Success", justify="right", width=8)
        table.add_column("Queue", justify="right", width=6)

        status_colors = {
            "idle": "green",
            "working": "yellow",
            "waiting": "blue",
            "error": "red",
            "stopped": "dim",
        }

        for agent in self._agents:
            status = agent.status.value
            color = status_colors.get(status, "white")
            metrics = agent.metrics

            table.add_row(
                agent.name,
                f"[{color}]{status}[/{color}]",
                str(metrics.tasks_completed),
                f"{metrics.success_rate:.0f}%",
                str(agent._message_queue.qsize()),
            )

        # Add message bus stats
        bus_stats = self._message_bus.get_stats()
        info_text = (
            f"Queue: {bus_stats['queue_size']} | "
            f"History: {bus_stats['history_size']} | "
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )

        return Panel(table, subtitle=info_text)

    def _signal_handler(self) -> None:
        """Handle shutdown signals."""
        self._logger.info("Shutdown signal received")
        self._console.print("\n[bold yellow]Shutdown signal received...[/bold yellow]")
        self._running = False
        self._shutdown_event.set()

    async def shutdown(self) -> None:
        """Gracefully shutdown all components."""
        self._logger.info("Initiating graceful shutdown...")
        self._console.print("[bold yellow]Shutting down Agent Army...[/bold yellow]")

        # Stop all agents
        await self._registry.shutdown_all()

        # Stop message bus
        await self._message_bus.stop()

        # Stop registry
        await self._registry.stop()

        # Close database
        if self._database:
            await self._database.close()

        self._console.print("[bold green]Agent Army stopped.[/bold green]")

    async def get_status(self) -> dict[str, Any]:
        """Get current system status."""
        agent_status = []
        for agent in self._agents:
            health = await agent.health_check()
            agent_status.append(health)

        return {
            "running": self._running,
            "timestamp": datetime.now().isoformat(),
            "agents": agent_status,
            "message_bus": self._message_bus.get_stats(),
            "registry": self._registry.get_stats(),
        }

    async def get_report(self) -> dict[str, Any]:
        """Get daily report data."""
        if not self._database:
            return {}

        return await self._database.get_daily_report()


async def run_orchestrator(config_path: Optional[str] = None) -> None:
    """Run the orchestrator."""
    orchestrator = Orchestrator(config_path)
    await orchestrator.initialize()
    await orchestrator.start()
