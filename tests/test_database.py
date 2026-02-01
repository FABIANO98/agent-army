"""Tests for database operations."""

import pytest
from datetime import datetime

from src.agent_army.db import Database, DealStage
from src.agent_army.db.models import ProspectStatus, EmailStatus, ResponseCategory


class TestDatabase:
    """Tests for Database class."""

    @pytest.mark.asyncio
    async def test_database_initialization(self, database):
        """Test database can be initialized."""
        assert database is not None

    @pytest.mark.asyncio
    async def test_create_prospect(self, database):
        """Test prospect creation."""
        prospect = await database.create_prospect(
            name="Test AG",
            url="https://test-ag.ch",
            industry="bau",
            size="small",
            region="zürich",
            email="info@test-ag.ch",
            source="web_search",
        )

        assert prospect.id is not None
        assert prospect.name == "Test AG"
        assert prospect.status == ProspectStatus.NEW.value

    @pytest.mark.asyncio
    async def test_get_prospect(self, database):
        """Test prospect retrieval."""
        created = await database.create_prospect(
            name="Test GmbH",
            url="https://test-gmbh.ch",
        )

        found = await database.get_prospect(created.id)
        assert found is not None
        assert found.name == "Test GmbH"

    @pytest.mark.asyncio
    async def test_prospect_exists(self, database):
        """Test prospect existence check."""
        await database.create_prospect(
            name="Existing AG",
            url="https://existing.ch",
        )

        exists = await database.prospect_exists("https://existing.ch")
        assert exists is True

        not_exists = await database.prospect_exists("https://notexisting.ch")
        assert not_exists is False

    @pytest.mark.asyncio
    async def test_update_prospect_status(self, database):
        """Test prospect status update."""
        prospect = await database.create_prospect(
            name="Status Test AG",
            url="https://status-test.ch",
        )

        await database.update_prospect_status(prospect.id, ProspectStatus.CONTACTED)

        updated = await database.get_prospect(prospect.id)
        assert updated.status == ProspectStatus.CONTACTED.value

    @pytest.mark.asyncio
    async def test_create_company_profile(self, database):
        """Test company profile creation."""
        prospect = await database.create_prospect(
            name="Profile Test AG",
            url="https://profile-test.ch",
        )

        profile = await database.create_company_profile(
            prospect_id=prospect.id,
            ceo_name="Hans Muster",
            ceo_email="hans@profile-test.ch",
            employees_count=25,
            website_problems=["Nicht mobile-optimiert", "Langsame Ladezeit"],
            budget_estimate="medium",
            sentiment_score=7.5,
        )

        assert profile.id is not None
        assert profile.ceo_name == "Hans Muster"
        assert profile.sentiment_score == 7.5

        # Check prospect status was updated
        updated_prospect = await database.get_prospect(prospect.id)
        assert updated_prospect.status == ProspectStatus.RESEARCHED.value

    @pytest.mark.asyncio
    async def test_create_email(self, database):
        """Test email creation."""
        prospect = await database.create_prospect(
            name="Email Test AG",
            url="https://email-test.ch",
        )

        email = await database.create_email(
            prospect_id=prospect.id,
            subject="Test Subject",
            body="Test Body Content",
            email_type="cold_outreach",
        )

        assert email.id is not None
        assert email.subject == "Test Subject"
        assert email.status == EmailStatus.DRAFT.value

    @pytest.mark.asyncio
    async def test_update_email_status(self, database):
        """Test email status update."""
        prospect = await database.create_prospect(
            name="Email Status Test",
            url="https://email-status.ch",
        )

        email = await database.create_email(
            prospect_id=prospect.id,
            subject="Status Test",
            body="Body",
        )

        await database.update_email_status(
            email.id,
            EmailStatus.SENT,
            sent_at=datetime.now(),
        )

        updated = await database.get_email(email.id)
        assert updated.status == EmailStatus.SENT.value
        assert updated.sent_at is not None

    @pytest.mark.asyncio
    async def test_create_response(self, database):
        """Test response creation."""
        prospect = await database.create_prospect(
            name="Response Test",
            url="https://response-test.ch",
        )

        email = await database.create_email(
            prospect_id=prospect.id,
            subject="Original Email",
            body="Body",
        )

        response = await database.create_response(
            email_id=email.id,
            response_text="Danke für Ihre Nachricht. Wir sind interessiert.",
            subject="Re: Original Email",
            sentiment="positive",
            category=ResponseCategory.POSITIVE.value,
            meeting_requested=True,
        )

        assert response.id is not None
        assert response.category == ResponseCategory.POSITIVE.value
        assert response.meeting_requested is True

    @pytest.mark.asyncio
    async def test_create_deal(self, database):
        """Test deal creation."""
        prospect = await database.create_prospect(
            name="Deal Test AG",
            url="https://deal-test.ch",
        )

        deal = await database.create_deal(
            prospect_id=prospect.id,
            stage=DealStage.CONTACTED,
            value=5000.0,
        )

        assert deal.id is not None
        assert deal.stage == DealStage.CONTACTED.value
        assert deal.value == 5000.0

    @pytest.mark.asyncio
    async def test_update_deal_stage(self, database):
        """Test deal stage update."""
        prospect = await database.create_prospect(
            name="Stage Test",
            url="https://stage-test.ch",
        )

        deal = await database.create_deal(
            prospect_id=prospect.id,
            stage=DealStage.COLD_PROSPECT,
        )

        await database.update_deal_stage(deal.id, DealStage.RESPONDED)

        updated = await database.get_deal(deal.id)
        assert updated.stage == DealStage.RESPONDED.value

    @pytest.mark.asyncio
    async def test_get_pipeline_stats(self, database):
        """Test pipeline statistics."""
        # Create some deals at different stages
        for i, stage in enumerate([DealStage.COLD_PROSPECT, DealStage.CONTACTED, DealStage.WON]):
            prospect = await database.create_prospect(
                name=f"Pipeline Test {i}",
                url=f"https://pipeline{i}.ch",
            )
            await database.create_deal(
                prospect_id=prospect.id,
                stage=stage,
                value=1000.0 * (i + 1),
            )

        stats = await database.get_pipeline_stats()

        assert "stages" in stats
        assert "total" in stats
        assert stats["total"]["count"] == 3

    @pytest.mark.asyncio
    async def test_get_daily_report(self, database):
        """Test daily report generation."""
        # Create some test data
        prospect = await database.create_prospect(
            name="Report Test",
            url="https://report-test.ch",
        )

        email = await database.create_email(
            prospect_id=prospect.id,
            subject="Report Email",
            body="Body",
        )
        await database.update_email_status(email.id, EmailStatus.SENT, sent_at=datetime.now())

        report = await database.get_daily_report()

        assert "date" in report
        assert "prospects_found" in report
        assert "emails_sent" in report
        assert "pipeline" in report

    @pytest.mark.asyncio
    async def test_agent_log(self, database):
        """Test agent log creation and retrieval."""
        await database.log_agent_activity(
            agent_id="test_agent_123",
            agent_name="TestAgent",
            message="Test log message",
            level="INFO",
            context={"task": "testing"},
        )

        logs = await database.get_agent_logs(agent_id="test_agent_123")

        assert len(logs) == 1
        assert logs[0].message == "Test log message"
        assert logs[0].level == "INFO"
