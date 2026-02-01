"""Pytest configuration and fixtures."""

import asyncio
import os
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio

from src.agent_army.core import MessageBus, AgentRegistry
from src.agent_army.db import Database
from src.agent_army.utils import Settings


@pytest.fixture(scope="function")
def event_loop():
    """Create event loop for each test function."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def database() -> AsyncGenerator[Database, None]:
    """Create test database."""
    # Use unique database name for each test to avoid conflicts
    db_name = f"/tmp/test_{uuid.uuid4().hex}.db"
    db = Database(f"sqlite+aiosqlite:///{db_name}")
    await db.init_db(drop_existing=True)
    yield db
    await db.close()
    # Cleanup
    if os.path.exists(db_name):
        try:
            os.remove(db_name)
        except Exception:
            pass


@pytest_asyncio.fixture(scope="function")
async def message_bus() -> AsyncGenerator[MessageBus, None]:
    """Create test message bus."""
    bus = MessageBus()
    await bus.start()
    yield bus
    await bus.stop()


@pytest_asyncio.fixture(scope="function")
async def registry() -> AsyncGenerator[AgentRegistry, None]:
    """Create test registry."""
    reg = AgentRegistry(health_check_interval=60)
    await reg.start()
    yield reg
    await reg.stop()


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings()
