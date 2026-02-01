"""Tests for individual agents."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agent_army.agents import (
    ProspectFinderAgent,
    ResearchManagerAgent,
    EmailWriterAgent,
    QualityControlAgent,
    EmailSenderAgent,
    ResponseMonitorAgent,
    ResponseWriterAgent,
    DealTrackerAgent,
)
from src.agent_army.core import AgentStatus, MessageType


class TestProspectFinderAgent:
    """Tests for ProspectFinder agent."""

    @pytest.mark.asyncio
    async def test_agent_creation(self, message_bus, registry, database, settings):
        """Test agent can be created."""
        agent = ProspectFinderAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        assert agent.name == "ProspectFinder"
        assert agent.agent_type == "prospect_finder"
        assert agent.status == AgentStatus.IDLE

    @pytest.mark.asyncio
    async def test_agent_start_stop(self, message_bus, registry, database, settings):
        """Test agent can start and stop."""
        agent = ProspectFinderAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        await agent.start()
        assert agent.is_running

        await agent.stop()
        assert not agent.is_running


class TestResearchManagerAgent:
    """Tests for ResearchManager agent."""

    @pytest.mark.asyncio
    async def test_agent_creation(self, message_bus, registry, database, settings):
        """Test agent can be created."""
        agent = ResearchManagerAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        assert agent.name == "ResearchManager"
        assert agent.agent_type == "research_manager"


class TestEmailWriterAgent:
    """Tests for EmailWriter agent."""

    @pytest.mark.asyncio
    async def test_agent_creation(self, message_bus, registry, database, settings):
        """Test agent can be created."""
        agent = EmailWriterAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        assert agent.name == "EmailWriter"
        assert agent.agent_type == "email_writer"

    @pytest.mark.asyncio
    async def test_determine_anrede(self, message_bus, registry, database, settings):
        """Test salutation determination."""
        agent = EmailWriterAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        assert agent._determine_anrede("Peter Müller") == "Herr"
        assert agent._determine_anrede("Maria Schmidt") == "Frau"
        assert agent._determine_anrede("Unknown Name") == "Herr/Frau"


class TestQualityControlAgent:
    """Tests for QualityControl agent."""

    @pytest.mark.asyncio
    async def test_agent_creation(self, message_bus, registry, database, settings):
        """Test agent can be created."""
        agent = QualityControlAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        assert agent.name == "QualityControl"
        assert agent.agent_type == "quality_control"

    @pytest.mark.asyncio
    async def test_placeholder_check(self, message_bus, registry, database, settings):
        """Test placeholder detection."""
        agent = QualityControlAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        # Clean text
        result = agent._check_placeholders("Guten Tag Herr Müller, hier ist Ihr Angebot.")
        assert result["ok"] is True

        # Text with placeholders
        result = agent._check_placeholders("Guten Tag {{NAME}}, hier ist {{FIRMA}}.")
        assert result["ok"] is False
        assert "{{NAME}}" in result["found"]

    @pytest.mark.asyncio
    async def test_call_to_action_check(self, message_bus, registry, database, settings):
        """Test CTA detection."""
        agent = QualityControlAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        # With CTA
        text = "Ich würde mich freuen, wenn wir einen Termin vereinbaren könnten."
        result = agent._check_call_to_action(text)
        assert result["ok"] is True

        # Without CTA
        text = "Das ist ein sehr langer Text ohne irgendwelche Handlungsaufforderung am Ende."
        result = agent._check_call_to_action(text)
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_subject_line_check(self, message_bus, registry, database, settings):
        """Test subject line validation."""
        agent = QualityControlAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        # Good subject
        result = agent._check_subject_line("Kurze Frage zu Müller AG")
        assert result["ok"] is True

        # Subject with too many exclamation marks
        result = agent._check_subject_line("UNGLAUBLICHES ANGEBOT!!!")
        assert result["ok"] is False


class TestEmailSenderAgent:
    """Tests for EmailSender agent."""

    @pytest.mark.asyncio
    async def test_agent_creation(self, message_bus, registry, database, settings):
        """Test agent can be created."""
        agent = EmailSenderAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        assert agent.name == "EmailSender"
        assert agent.agent_type == "email_sender"

    @pytest.mark.asyncio
    async def test_optimal_send_time(self, message_bus, registry, database, settings):
        """Test optimal send time detection."""
        from datetime import datetime

        agent = EmailSenderAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        # Weekday at 10:00
        weekday_morning = datetime(2024, 1, 15, 10, 0)  # Monday
        assert agent._is_optimal_send_time(weekday_morning) is True

        # Weekend
        weekend = datetime(2024, 1, 20, 10, 0)  # Saturday
        assert agent._is_optimal_send_time(weekend) is False

        # Late night
        late_night = datetime(2024, 1, 15, 23, 0)
        assert agent._is_optimal_send_time(late_night) is False


class TestResponseMonitorAgent:
    """Tests for ResponseMonitor agent."""

    @pytest.mark.asyncio
    async def test_agent_creation(self, message_bus, registry, database, settings):
        """Test agent can be created."""
        agent = ResponseMonitorAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        assert agent.name == "ResponseMonitor"
        assert agent.agent_type == "response_monitor"

    @pytest.mark.asyncio
    async def test_response_categorization(self, message_bus, registry, database, settings):
        """Test response categorization."""
        from src.agent_army.db.models import ResponseCategory

        agent = ResponseMonitorAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        # Positive response
        positive = {"body": "Danke, das interessiert uns sehr! Können wir einen Termin machen?"}
        assert agent._categorize_response(positive) == ResponseCategory.POSITIVE

        # Negative response
        negative = {"body": "Wir haben kein Interesse. Bitte kontaktieren Sie uns nicht mehr."}
        assert agent._categorize_response(negative) == ResponseCategory.NEGATIVE

        # Out of office
        ooo = {"body": "Ich bin bis zum 15. Januar im Urlaub.", "subject": "Automatische Antwort"}
        assert agent._categorize_response(ooo) == ResponseCategory.OUT_OF_OFFICE

        # Question
        question = {"body": "Was kostet das ungefähr?"}
        assert agent._categorize_response(question) == ResponseCategory.QUESTION

    @pytest.mark.asyncio
    async def test_sentiment_analysis(self, message_bus, registry, database, settings):
        """Test sentiment analysis."""
        agent = ResponseMonitorAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        positive_text = "Vielen Dank für Ihr tolles Angebot! Das klingt super."
        assert agent._analyze_sentiment(positive_text) == "positive"

        negative_text = "Leider haben wir kein Interesse. Das passt nicht zu uns."
        assert agent._analyze_sentiment(negative_text) == "negative"


class TestResponseWriterAgent:
    """Tests for ResponseWriter agent."""

    @pytest.mark.asyncio
    async def test_agent_creation(self, message_bus, registry, database, settings):
        """Test agent can be created."""
        agent = ResponseWriterAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        assert agent.name == "ResponseWriter"
        assert agent.agent_type == "response_writer"

    @pytest.mark.asyncio
    async def test_time_slot_generation(self, message_bus, registry, database, settings):
        """Test time slot generation."""
        agent = ResponseWriterAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        slots = agent._generate_time_slots()

        assert len(slots) == 3
        assert "10:00" in slots[0] or "14:00" in slots[0]


class TestDealTrackerAgent:
    """Tests for DealTracker agent."""

    @pytest.mark.asyncio
    async def test_agent_creation(self, message_bus, registry, database, settings):
        """Test agent can be created."""
        agent = DealTrackerAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        assert agent.name == "DealTracker"
        assert agent.agent_type == "deal_tracker"

    @pytest.mark.asyncio
    async def test_report_formatting(self, message_bus, registry, database, settings):
        """Test report formatting."""
        agent = DealTrackerAgent(
            message_bus=message_bus,
            registry=registry,
            database=database,
            settings=settings,
        )

        report = {
            "date": "2024-01-15",
            "prospects_found": 10,
            "emails_sent": 5,
            "responses_received": 2,
            "positive_responses": 1,
        }
        pipeline = {
            "stages": {
                "cold_prospect": {"count": 50, "value": 0},
                "contacted": {"count": 20, "value": 0},
                "won": {"count": 3, "value": 15000},
            },
            "total": {"count": 73, "value": 15000},
        }

        formatted = agent._format_report(report, pipeline)

        assert "DAILY REPORT" in formatted
        assert "2024-01-15" in formatted
        assert "Prospects found" in formatted
