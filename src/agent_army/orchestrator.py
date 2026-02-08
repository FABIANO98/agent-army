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
    TaskManagerAgent,
)
from .core import AgentRegistry, MessageBus
from .core.llm_service import LLMService
from .db import Database
from .scrapers.browser_manager import BrowserManager
from .scrapers.website_analyzer import WebsiteAnalyzer
from .scrapers.zefix_client import ZefixClient
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
    - Run FastAPI web server
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        self._settings = load_config(config_path)
        self._console = Console()
        self._message_bus = MessageBus()
        self._registry = AgentRegistry()
        self._database: Optional[Database] = None
        self._llm_service: Optional[LLMService] = None
        self._browser_manager: Optional[BrowserManager] = None
        self._zefix_client: Optional[ZefixClient] = None
        self._website_analyzer: Optional[WebsiteAnalyzer] = None
        self._task_manager: Optional[TaskManagerAgent] = None
        self._agents: list[Any] = []
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._logger = logger.bind(component="Orchestrator")

    async def initialize(self) -> None:
        """Initialize all components."""
        setup_logging(self._settings.logging)
        self._logger.info("Initializing Agent Army...")

        # Initialize database
        self._database = Database(
            self._settings.database.database_url,
            echo=self._settings.database.echo_sql,
        )
        await self._database.init_db()
        self._logger.info("Database initialized")

        # Initialize LLM service
        if self._settings.llm.api_key:
            self._llm_service = LLMService(
                api_key=self._settings.llm.api_key,
                default_model=self._settings.llm.default_model,
                fast_model=self._settings.llm.fast_model,
                max_concurrent=self._settings.llm.max_concurrent,
                requests_per_minute=self._settings.llm.requests_per_minute,
            )
            await self._llm_service.initialize()
            self._logger.info("LLM service initialized")
        else:
            self._logger.info("No LLM API key configured - running without AI features")

        # Initialize scraping components
        self._browser_manager = BrowserManager(
            headless=self._settings.scraping.headless,
            max_concurrent_pages=self._settings.scraping.max_concurrent_pages,
            user_agent=self._settings.scraping.user_agent,
        )
        await self._browser_manager.start()

        self._zefix_client = ZefixClient()
        await self._zefix_client.start()

        self._website_analyzer = WebsiteAnalyzer(
            llm_service=self._llm_service,
            browser_manager=self._browser_manager,
        )
        self._logger.info("Scraping components initialized")

        # Start message bus
        await self._message_bus.start()
        self._logger.info("Message bus started")

        # Start registry
        await self._registry.start()
        self._logger.info("Agent registry started")

        # Create TaskManager
        self._task_manager = TaskManagerAgent(
            message_bus=self._message_bus,
            registry=self._registry,
            database=self._database,
            settings=self._settings,
            llm_service=self._llm_service,
        )

        # Shared constructor kwargs
        base_kwargs: dict[str, Any] = {
            "message_bus": self._message_bus,
            "registry": self._registry,
            "database": self._database,
            "settings": self._settings,
        }
        llm_kwargs = {**base_kwargs, "llm_service": self._llm_service}

        # Create all agents
        self._agents = [
            self._task_manager,
            ProspectFinderAgent(**base_kwargs, zefix_client=self._zefix_client),
            ResearchManagerAgent(
                **llm_kwargs,
                browser_manager=self._browser_manager,
                website_analyzer=self._website_analyzer,
            ),
            EmailWriterAgent(**llm_kwargs),
            QualityControlAgent(**llm_kwargs),
            EmailSenderAgent(**base_kwargs),
            ResponseMonitorAgent(**llm_kwargs),
            ResponseWriterAgent(**llm_kwargs),
            DealTrackerAgent(**llm_kwargs),
        ]

        # Register agents with message bus
        for agent in self._agents:
            self._message_bus.register_agent(agent)

        self._logger.info(f"Created {len(self._agents)} agents")

    async def start(self) -> None:
        """Start all agents and begin orchestration."""
        self._running = True

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._signal_handler)

        self._logger.info("Starting all agents...")
        self._console.print("[bold green]Starting Agent Army...[/bold green]")

        start_tasks = [agent.start() for agent in self._agents]
        await asyncio.gather(*start_tasks)

        self._console.print(f"[bold green]{len(self._agents)} agents started![/bold green]")

        try:
            await self._run_with_display()
        except asyncio.CancelledError:
            pass

        await self.shutdown()

    async def start_with_web(self, port: int = 8000) -> None:
        """Start agents and web server together."""
        self._running = True

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._signal_handler)

        self._logger.info("Starting all agents...")
        self._console.print("[bold green]Starting Agent Army with Web Dashboard...[/bold green]")

        start_tasks = [agent.start() for agent in self._agents]
        await asyncio.gather(*start_tasks)

        self._console.print(f"[bold green]{len(self._agents)} agents started![/bold green]")

        # Start FastAPI server
        web_task = asyncio.create_task(self._start_web_server(port))
        self._console.print(f"[bold cyan]Web Dashboard: http://localhost:{port}[/bold cyan]")

        try:
            await self._run_with_display()
        except asyncio.CancelledError:
            pass

        web_task.cancel()
        try:
            await web_task
        except asyncio.CancelledError:
            pass

        await self.shutdown()

    async def _start_web_server(self, port: int) -> None:
        """Start the uvicorn web server."""
        try:
            import uvicorn
            from .api.app import create_app

            app = create_app(
                orchestrator=self,
                database=self._database,
                task_manager=self._task_manager,
            )

            config = uvicorn.Config(
                app,
                host="0.0.0.0",
                port=port,
                log_level="warning",
            )
            server = uvicorn.Server(config)
            await server.serve()
        except ImportError:
            self._logger.warning("uvicorn not installed - web server disabled")
        except asyncio.CancelledError:
            pass

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

        bus_stats = self._message_bus.get_stats()
        llm_status = "ON" if self._llm_service and self._llm_service.is_available else "OFF"
        info_text = (
            f"Queue: {bus_stats['queue_size']} | "
            f"History: {bus_stats['history_size']} | "
            f"LLM: {llm_status} | "
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )

        return Panel(table, subtitle=info_text)

    def _signal_handler(self) -> None:
        self._logger.info("Shutdown signal received")
        self._console.print("\n[bold yellow]Shutdown signal received...[/bold yellow]")
        self._running = False
        self._shutdown_event.set()

    async def shutdown(self) -> None:
        """Gracefully shutdown all components."""
        self._logger.info("Initiating graceful shutdown...")
        self._console.print("[bold yellow]Shutting down Agent Army...[/bold yellow]")

        await self._registry.shutdown_all()
        await self._message_bus.stop()
        await self._registry.stop()

        # Stop scraping components
        if self._browser_manager:
            await self._browser_manager.stop()
        if self._zefix_client:
            await self._zefix_client.stop()

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
            "llm_available": self._llm_service.is_available if self._llm_service else False,
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


async def run_orchestrator_with_web(
    config_path: Optional[str] = None, port: int = 8000
) -> None:
    """Run the orchestrator with web server."""
    orchestrator = Orchestrator(config_path)
    await orchestrator.initialize()
    await orchestrator.start_with_web(port=port)
