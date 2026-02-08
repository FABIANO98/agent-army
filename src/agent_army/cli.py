"""CLI interface for Agent Army."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .orchestrator import Orchestrator, run_orchestrator, run_orchestrator_with_web
from .utils.config import create_default_config, load_config


console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="agent-army")
def main() -> None:
    """Agent Army - Multi-Agent Lead Generation System for B2B Sales Automation."""
    pass


@main.command()
@click.option(
    "--config", "-c",
    type=click.Path(exists=False),
    help="Path to configuration file",
)
def start(config: Optional[str]) -> None:
    """Start all agents."""
    console.print(Panel.fit(
        "[bold cyan]Agent Army[/bold cyan]\n"
        "Multi-Agent Lead Generation System",
        border_style="cyan",
    ))

    try:
        asyncio.run(run_orchestrator(config))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")


@main.command()
@click.option(
    "--config", "-c",
    type=click.Path(exists=False),
    help="Path to configuration file",
)
def status(config: Optional[str]) -> None:
    """Show agent status."""
    async def get_status() -> None:
        orchestrator = Orchestrator(config)
        await orchestrator.initialize()

        status_data = await orchestrator.get_status()

        table = Table(title="Agent Status", show_header=True, header_style="bold cyan")
        table.add_column("Agent", style="dim")
        table.add_column("Status")
        table.add_column("Running")
        table.add_column("Tasks")
        table.add_column("Success Rate")

        for agent in status_data.get("agents", []):
            metrics = agent.get("metrics", {})
            table.add_row(
                agent.get("name", "Unknown"),
                agent.get("status", "unknown"),
                "Yes" if agent.get("running") else "No",
                str(metrics.get("tasks_completed", 0)),
                f"{metrics.get('success_rate', 0):.0f}%",
            )

        console.print(table)

        # Message bus stats
        bus_stats = status_data.get("message_bus", {})
        console.print(f"\nMessage Bus: Queue={bus_stats.get('queue_size', 0)}, "
                      f"History={bus_stats.get('history_size', 0)}")

        await orchestrator.shutdown()

    try:
        asyncio.run(get_status())
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@main.command()
@click.option(
    "--config", "-c",
    type=click.Path(exists=False),
    help="Path to configuration file",
)
def report(config: Optional[str]) -> None:
    """Show daily report."""
    async def get_report() -> None:
        orchestrator = Orchestrator(config)
        await orchestrator.initialize()

        report_data = await orchestrator.get_report()

        if not report_data:
            console.print("[yellow]No report data available[/yellow]")
            await orchestrator.shutdown()
            return

        # Activity summary
        console.print(Panel.fit(
            f"[bold]Daily Report - {report_data.get('date', 'Today')}[/bold]",
            border_style="cyan",
        ))

        activity_table = Table(show_header=False)
        activity_table.add_column("Metric", style="dim")
        activity_table.add_column("Value", justify="right")

        activity_table.add_row("Prospects Found", str(report_data.get("prospects_found", 0)))
        activity_table.add_row("Emails Sent", str(report_data.get("emails_sent", 0)))
        activity_table.add_row("Responses Received", str(report_data.get("responses_received", 0)))
        activity_table.add_row("Positive Responses", str(report_data.get("positive_responses", 0)))

        console.print(activity_table)

        # Pipeline
        pipeline = report_data.get("pipeline", {})
        stages = pipeline.get("stages", {})

        if stages:
            console.print("\n[bold]Pipeline[/bold]")
            pipeline_table = Table(show_header=True, header_style="bold")
            pipeline_table.add_column("Stage")
            pipeline_table.add_column("Count", justify="right")
            pipeline_table.add_column("Value (CHF)", justify="right")

            for stage, data in stages.items():
                count = data.get("count", 0)
                value = data.get("value", 0)
                if count > 0:
                    pipeline_table.add_row(
                        stage.replace("_", " ").title(),
                        str(count),
                        f"{value:,.0f}" if value else "-",
                    )

            console.print(pipeline_table)

        await orchestrator.shutdown()

    try:
        asyncio.run(get_report())
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@main.command()
@click.option(
    "--config", "-c",
    type=click.Path(exists=False),
    help="Path to configuration file",
)
@click.option(
    "--agent", "-a",
    type=str,
    help="Filter logs by agent name",
)
@click.option(
    "--level", "-l",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    default="INFO",
    help="Minimum log level",
)
@click.option(
    "--follow", "-f",
    is_flag=True,
    help="Follow logs in real-time",
)
def logs(config: Optional[str], agent: Optional[str], level: str, follow: bool) -> None:
    """Show agent logs."""
    async def show_logs() -> None:
        orchestrator = Orchestrator(config)
        await orchestrator.initialize()

        if not orchestrator._database:
            console.print("[yellow]No database available[/yellow]")
            return

        logs_data = await orchestrator._database.get_agent_logs(
            agent_id=agent,
            level=level if level != "INFO" else None,
            limit=50,
        )

        if not logs_data:
            console.print("[yellow]No logs found[/yellow]")
            await orchestrator.shutdown()
            return

        table = Table(show_header=True, header_style="bold")
        table.add_column("Time", style="dim", width=10)
        table.add_column("Agent", width=15)
        table.add_column("Level", width=8)
        table.add_column("Message")

        level_colors = {
            "DEBUG": "dim",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
        }

        for log in reversed(logs_data):
            timestamp = log.timestamp.strftime("%H:%M:%S") if log.timestamp else ""
            color = level_colors.get(log.level, "white")
            table.add_row(
                timestamp,
                log.agent_name,
                f"[{color}]{log.level}[/{color}]",
                log.message[:80] + "..." if len(log.message) > 80 else log.message,
            )

        console.print(table)
        await orchestrator.shutdown()

    try:
        asyncio.run(show_logs())
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@main.command()
@click.argument("path", type=click.Path(), default="config.yaml")
def init(path: str) -> None:
    """Initialize configuration file."""
    config_path = Path(path)

    if config_path.exists():
        if not click.confirm(f"{path} already exists. Overwrite?"):
            return

    create_default_config(config_path)
    console.print(f"[green]Configuration created: {path}[/green]")
    console.print("\nNext steps:")
    console.print("1. Edit the configuration file with your settings")
    console.print("2. Add your API keys and email credentials")
    console.print("3. Run 'agent-army start' to begin")


@main.command()
@click.option(
    "--config", "-c",
    type=click.Path(exists=False),
    help="Path to configuration file",
)
@click.option(
    "--port", "-p",
    type=int,
    default=8000,
    help="Web server port",
)
def web(config: Optional[str], port: int) -> None:
    """Start agents with web dashboard."""
    console.print(Panel.fit(
        "[bold cyan]Agent Army[/bold cyan]\n"
        "Web Dashboard Mode",
        border_style="cyan",
    ))

    try:
        asyncio.run(run_orchestrator_with_web(config, port=port))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")


@main.command()
def stop() -> None:
    """Stop all agents (sends SIGTERM to running process)."""
    import os
    import subprocess

    # Find running agent-army process
    try:
        result = subprocess.run(
            ["pgrep", "-f", "agent-army start"],
            capture_output=True,
            text=True,
        )
        pids = result.stdout.strip().split("\n")

        if pids and pids[0]:
            for pid in pids:
                if pid:
                    os.kill(int(pid), 15)  # SIGTERM
                    console.print(f"[yellow]Sent stop signal to PID {pid}[/yellow]")
        else:
            console.print("[yellow]No running agent-army process found[/yellow]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@main.command()
def version() -> None:
    """Show version information."""
    from . import __version__

    console.print(Panel.fit(
        f"[bold cyan]Agent Army[/bold cyan]\n"
        f"Version: {__version__}\n"
        f"Multi-Agent Lead Generation System",
        border_style="cyan",
    ))


if __name__ == "__main__":
    main()
