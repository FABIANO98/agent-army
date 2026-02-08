"""Configuration management for the Agent Army system."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailSettings(BaseSettings):
    """Email configuration settings."""

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True

    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""

    from_name: str = "Fabiano Frascati"
    from_email: str = ""
    signature: str = """
Mit freundlichen Grüssen,

Fabiano Frascati
Frascati Systems
Web Development & Digital Solutions

Tel: +41 XX XXX XX XX
Web: www.frascati-systems.ch
"""


class LLMSettings(BaseSettings):
    """LLM/Claude API configuration."""

    api_key: str = ""
    default_model: str = "claude-sonnet-4-5-20250929"
    fast_model: str = "claude-haiku-4-5-20251001"
    max_concurrent: int = 5
    requests_per_minute: int = 50


class ScrapingSettings(BaseSettings):
    """Web scraping configuration."""

    headless: bool = True
    max_concurrent_pages: int = 3
    request_delay: float = 2.0
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


class APISettings(BaseSettings):
    """API keys configuration."""

    hunter_api_key: str = ""
    openai_api_key: str = ""
    sendgrid_api_key: str = ""
    languagetool_api_key: str = ""


class AgentSettings(BaseSettings):
    """Agent behavior settings."""

    # ProspectFinder
    prospect_finder_interval: int = 3600  # 1 hour
    daily_prospect_target: int = 20
    target_industries: list[str] = Field(
        default=["bau", "transport", "logistik", "handwerk", "gastronomie"]
    )
    target_regions: list[str] = Field(
        default=["zürich", "bern", "basel", "luzern", "st. gallen"]
    )

    # ResearchManager
    research_manager_interval: int = 1800  # 30 minutes
    max_research_per_batch: int = 5

    # EmailWriter
    email_writer_interval: int = 600  # 10 minutes

    # QualityControl
    min_personalization_score: int = 7
    min_email_words: int = 150
    max_email_words: int = 250

    # EmailSender
    email_sender_interval: int = 300  # 5 minutes
    daily_email_limit: int = 50
    optimal_send_hour: int = 10  # 10:00 Swiss time
    follow_up_days: int = 3

    # ResponseMonitor
    response_monitor_interval: int = 1800  # 30 minutes

    # DealTracker
    deal_tracker_interval: int = 3600  # 1 hour
    daily_report_hour: int = 18  # 18:00
    stale_lead_days: int = 7


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    database_url: str = "sqlite+aiosqlite:///./agent_army.db"
    echo_sql: bool = False


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    level: str = "INFO"
    format: str = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[component]}</cyan> | "
        "<level>{message}</level>"
    )
    file_path: Optional[str] = "./logs/agent_army.log"
    rotation: str = "10 MB"
    retention: str = "7 days"


class Settings(BaseSettings):
    """Main settings for the Agent Army system."""

    model_config = SettingsConfigDict(
        env_prefix="AGENT_ARMY_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Sub-settings
    email: EmailSettings = Field(default_factory=EmailSettings)
    api: APISettings = Field(default_factory=APISettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    scraping: ScrapingSettings = Field(default_factory=ScrapingSettings)
    agents: AgentSettings = Field(default_factory=AgentSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    # General settings
    debug: bool = False
    environment: str = "development"

    @classmethod
    def from_yaml(cls, path: Path) -> "Settings":
        """
        Load settings from a YAML file.

        Args:
            path: Path to the YAML configuration file

        Returns:
            Settings instance
        """
        if not path.exists():
            return cls()

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        return cls(**data)


def load_config(config_path: Optional[str] = None) -> Settings:
    """
    Load configuration from file or defaults.

    Args:
        config_path: Optional path to config file

    Returns:
        Settings instance
    """
    if config_path:
        path = Path(config_path)
        if path.exists():
            return Settings.from_yaml(path)

    # Try default locations
    default_paths = [
        Path("config.yaml"),
        Path("config/config.yaml"),
        Path.home() / ".agent-army" / "config.yaml",
    ]

    for path in default_paths:
        if path.exists():
            return Settings.from_yaml(path)

    return Settings()


def create_default_config(path: Path) -> None:
    """
    Create a default configuration file.

    Args:
        path: Path where to create the config file
    """
    default_config: dict[str, Any] = {
        "debug": False,
        "environment": "development",
        "email": {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_username": "",
            "smtp_password": "",
            "smtp_use_tls": True,
            "imap_host": "imap.gmail.com",
            "imap_port": 993,
            "imap_username": "",
            "imap_password": "",
            "from_name": "Fabiano Frascati",
            "from_email": "",
            "signature": """
Mit freundlichen Grüssen,

Fabiano Frascati
Frascati Systems
Web Development & Digital Solutions
""",
        },
        "api": {
            "hunter_api_key": "",
            "openai_api_key": "",
            "sendgrid_api_key": "",
            "languagetool_api_key": "",
        },
        "agents": {
            "prospect_finder_interval": 3600,
            "daily_prospect_target": 20,
            "target_industries": ["bau", "transport", "logistik", "handwerk"],
            "target_regions": ["zürich", "bern", "basel", "luzern"],
            "research_manager_interval": 1800,
            "email_sender_interval": 300,
            "daily_email_limit": 50,
            "optimal_send_hour": 10,
            "follow_up_days": 3,
            "response_monitor_interval": 1800,
            "daily_report_hour": 18,
            "stale_lead_days": 7,
        },
        "database": {
            "database_url": "sqlite+aiosqlite:///./agent_army.db",
            "echo_sql": False,
        },
        "logging": {
            "level": "INFO",
            "file_path": "./logs/agent_army.log",
            "rotation": "10 MB",
            "retention": "7 days",
        },
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)
