"""Tests for core components."""

import asyncio
from datetime import datetime

import pytest

from src.agent_army.core import BaseAgent, AgentStatus, MessageBus, Message, Priority, AgentRegistry


class MockAgent(BaseAgent):
    """Mock agent for testing."""

    def __init__(self, name: str = "MockAgent", **kwargs):
        super().__init__(name=name, agent_type="mock", **kwargs)
        self.processed_messages = []
        self.run_count = 0

    async def run(self) -> None:
        self.run_count += 1
        await asyncio.sleep(0.1)

    async def process_message(self, message: Message) -> None:
        self.processed_messages.append(message)


class TestBaseAgent:
    """Tests for BaseAgent class."""

    @pytest.mark.asyncio
    async def test_agent_creation(self):
        """Test agent can be created with correct attributes."""
        agent = MockAgent(name="TestAgent")

        assert agent.name == "TestAgent"
        assert agent.agent_type == "mock"
        assert agent.status == AgentStatus.IDLE
        assert not agent.is_running
        assert agent.agent_id.startswith("mock_")

    @pytest.mark.asyncio
    async def test_agent_start_stop(self, message_bus, registry):
        """Test agent can start and stop."""
        agent = MockAgent(
            name="TestAgent",
            message_bus=message_bus,
            registry=registry,
        )

        await agent.start()
        assert agent.is_running
        assert agent.status == AgentStatus.IDLE

        # Wait longer for the run loop to execute
        await asyncio.sleep(0.5)

        await agent.stop()
        assert not agent.is_running
        assert agent.status == AgentStatus.STOPPED

    @pytest.mark.asyncio
    async def test_agent_metrics(self, message_bus, registry):
        """Test agent metrics tracking."""
        agent = MockAgent(
            message_bus=message_bus,
            registry=registry,
        )

        await agent.start()
        await asyncio.sleep(0.3)

        metrics = agent.metrics
        assert metrics.tasks_completed >= 0
        assert metrics.success_rate == 100.0
        assert metrics.started_at is not None

        await agent.stop()

    @pytest.mark.asyncio
    async def test_agent_health_check(self, message_bus, registry):
        """Test agent health check."""
        agent = MockAgent(
            message_bus=message_bus,
            registry=registry,
        )

        await agent.start()
        health = await agent.health_check()

        assert health["agent_id"] == agent.agent_id
        assert health["name"] == agent.name
        assert health["running"] is True
        assert "metrics" in health

        await agent.stop()


class TestMessageBus:
    """Tests for MessageBus class."""

    @pytest.mark.asyncio
    async def test_message_bus_creation(self):
        """Test message bus can be created."""
        bus = MessageBus()
        assert bus._running is False

    @pytest.mark.asyncio
    async def test_message_bus_start_stop(self):
        """Test message bus can start and stop."""
        bus = MessageBus()
        await bus.start()
        assert bus._running is True

        await bus.stop()
        assert bus._running is False

    @pytest.mark.asyncio
    async def test_agent_registration(self, message_bus):
        """Test agents can be registered and discovered."""
        agent = MockAgent(name="TestAgent")
        message_bus.register_agent(agent)

        found = message_bus.get_agent(agent.agent_id)
        assert found == agent

        found_by_name = message_bus.get_agent("testagent")
        assert found_by_name == agent

        message_bus.unregister_agent(agent.agent_id)
        assert message_bus.get_agent(agent.agent_id) is None

    @pytest.mark.asyncio
    async def test_message_sending(self, message_bus):
        """Test messages can be sent and delivered."""
        agent1 = MockAgent(name="Agent1")
        agent2 = MockAgent(name="Agent2", message_bus=message_bus)

        message_bus.register_agent(agent1)
        message_bus.register_agent(agent2)

        msg_id = await message_bus.send(
            sender_id=agent1.agent_id,
            recipient_id=agent2.agent_id,
            message_type="test",
            payload={"data": "test"},
        )

        assert msg_id.startswith("msg_")
        await asyncio.sleep(0.2)

        assert len(agent2.processed_messages) == 0  # Not processed until started

    @pytest.mark.asyncio
    async def test_broadcast_message(self, message_bus):
        """Test broadcast messages reach all agents."""
        agents = [MockAgent(name=f"Agent{i}") for i in range(3)]
        for agent in agents:
            message_bus.register_agent(agent)

        await message_bus.send(
            sender_id="system",
            recipient_id="broadcast",
            message_type="announcement",
            payload={"text": "Hello all!"},
        )

        # Messages queued but not processed (agents not running)
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_message_priority(self, message_bus):
        """Test messages are processed by priority."""
        agent = MockAgent(name="TestAgent", message_bus=message_bus)
        message_bus.register_agent(agent)

        # Send messages with different priorities
        await message_bus.send(
            sender_id="system",
            recipient_id=agent.agent_id,
            message_type="low",
            payload={},
            priority="low",
        )
        await message_bus.send(
            sender_id="system",
            recipient_id=agent.agent_id,
            message_type="urgent",
            payload={},
            priority="urgent",
        )

        # Urgent should be processed first
        assert message_bus._priority_queue[0].priority == Priority.URGENT.value_int

    @pytest.mark.asyncio
    async def test_message_history(self, message_bus):
        """Test message history is maintained."""
        await message_bus.send(
            sender_id="system",
            recipient_id="broadcast",
            message_type="test1",
            payload={},
        )
        await message_bus.send(
            sender_id="system",
            recipient_id="broadcast",
            message_type="test2",
            payload={},
        )

        history = message_bus.get_history()
        assert len(history) == 2

        filtered = message_bus.get_history(message_type="test1")
        assert len(filtered) == 1

    @pytest.mark.asyncio
    async def test_mention_parsing(self, message_bus):
        """Test @mention parsing."""
        agent = MockAgent(name="TestAgent")
        message_bus.register_agent(agent)

        msg_id = await message_bus.send(
            sender_id="system",
            recipient_id="broadcast",
            message_type="test",
            payload={"text": "Hey @testagent check this!"},
        )

        history = message_bus.get_history()
        assert agent.agent_id in history[-1].mentions


class TestAgentRegistry:
    """Tests for AgentRegistry class."""

    @pytest.mark.asyncio
    async def test_registry_creation(self):
        """Test registry can be created."""
        registry = AgentRegistry()
        assert registry._running is False

    @pytest.mark.asyncio
    async def test_registry_start_stop(self):
        """Test registry can start and stop."""
        registry = AgentRegistry()
        await registry.start()
        assert registry._running is True

        await registry.stop()
        assert registry._running is False

    @pytest.mark.asyncio
    async def test_agent_registration(self, registry):
        """Test agents can be registered."""
        agent = MockAgent(name="TestAgent", registry=registry)
        await registry.register(agent)

        found = registry.get_agent(agent.agent_id)
        assert found == agent

        found_by_name = registry.get_agent_by_name("TestAgent")
        assert found_by_name == agent

    @pytest.mark.asyncio
    async def test_get_agents_by_type(self, registry):
        """Test getting agents by type."""
        agents = [MockAgent(name=f"Agent{i}", registry=registry) for i in range(3)]
        for agent in agents:
            await registry.register(agent)

        mock_agents = registry.get_agents_by_type("mock")
        assert len(mock_agents) == 3

    @pytest.mark.asyncio
    async def test_system_health(self, registry, message_bus):
        """Test system health check."""
        agent = MockAgent(
            name="TestAgent",
            registry=registry,
            message_bus=message_bus,
        )
        await agent.start()

        health = await registry.get_system_health()

        assert health["total_agents"] == 1
        assert health["healthy_agents"] == 1
        assert health["system_status"] == "healthy"

        await agent.stop()

    @pytest.mark.asyncio
    async def test_shutdown_all(self, registry, message_bus):
        """Test graceful shutdown of all agents."""
        agents = [
            MockAgent(name=f"Agent{i}", registry=registry, message_bus=message_bus)
            for i in range(3)
        ]
        for agent in agents:
            await agent.start()

        await registry.shutdown_all()

        for agent in agents:
            assert not agent.is_running
